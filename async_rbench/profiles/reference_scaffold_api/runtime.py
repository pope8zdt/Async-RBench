from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ...evaluation.case_contract import (
    MAX_INITIAL_WORKSTREAMS, public_delivery, public_rejection,
)
from ...evaluation.result_contract import validate_payload_contract
from ...evaluation.presentation import DeliveryOccurrence, PresentationQueue

from .config import ScaffoldConfig
from .gateway import DeliveryReader, ProtocolEmitter
from ...evaluation.budget import BudgetLedger, BudgetPool, Reservation, build_budget_ledger
from ...evaluation.model_backend import (
    ModelBackend, ModelTurn, ToolCall,
    conservative_input_estimate, function_tool,
)
from ...evaluation.workspace_runtime import CommandResult, WorkspaceRuntime


LOGGER = logging.getLogger("async_rbench.profiles.reference_scaffold_api")


def _role_seed(base: int, role: str) -> int:
    digest = hashlib.sha256(f"{base}:{role}".encode()).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def _trim(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n...[truncated {len(value) - limit} chars]"


def _tool_result(call_id: str, value: Any) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(value, ensure_ascii=False, sort_keys=True)}


def _estimate_input(backend: ModelBackend, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> tuple[int, str]:
    """Return ``(input_upper_bound, accounting_mode)`` for strict admission.

    Uses the backend's exact tokenizer when available (``accounting_mode``
    ``"provider_exact"``); otherwise falls back to a conservative upper bound
    and ``"conservative"`` so Track A can report how the pool accounted
    (spec §7.3).
    """
    estimator = getattr(backend, "estimate_input_tokens", None)
    if estimator is not None:
        estimate = estimator(messages=messages, tools=tools)
        return estimate.input_tokens, estimate.accounting_mode
    return conservative_input_estimate(messages, tools), "conservative"


# Modifying tools whose *completion* can establish a provisional boundary. Only
# these are handed to the post-tool observer (spec §4.1(1)); read/query tools and
# the participant-visible ``commit_artifact`` audit signal are deliberately
# excluded so a commit cannot itself create the only scored opportunity (§4.3).
OBSERVED_TOOLS = frozenset({"terminal", "promote_child_path"})

# Child lifecycle states that close a Linear wave slot for the atomic sync
# barrier. A child resolves when the benchmark wave releases a usable delivery,
# the gateway contract-rejects its completion, it is cancelled (timeout, stale
# redelegation), or the participant/delivery path marks it rejected. Anything
# still in ``queued``/``spawned``/``starting``/``running`` is unresolved, so the
# main model must keep waiting for the single terminal bundle.
LINEAR_TERMINAL_STATUSES = frozenset({
    "delivered", "contract_rejected", "cancelled", "rejected",
})


def emit_runtime_metadata_snapshot(backend: ModelBackend, emitter: ProtocolEmitter) -> None:
    """Persist provider-resolved identity before a later agent timeout can occur."""
    metadata = getattr(backend, "runtime_metadata", lambda: {"model_observations": []})()
    if metadata.get("model_observations"):
        emitter.emit("participant_runtime_metadata", **metadata)


@dataclass
class ChildRecord:
    child_id: str
    task: str
    work_units: list[str]
    targets: list[str]
    expected_output: str
    priority: str
    status: str = "queued"
    completion_id: str | None = None
    payload: Any = None
    tokens: int = 0
    delivery: dict[str, Any] | None = None
    contract_rejection: dict[str, Any] | None = None
    presented: bool = False
    decision: str | None = None
    asyncio_task: asyncio.Task | None = None
    initial_wave: bool = True
    required_evidence_fields: list[str] = field(default_factory=list)
    evidence_schema: dict[str, Any] = field(default_factory=dict)
    allowed_result_files: list[str] = field(default_factory=list)
    required_result_files: list[str] = field(default_factory=list)
    public_result_contract: dict[str, Any] = field(default_factory=dict)
    result_file_contract_enforced: bool = False


@dataclass
class EpisodeTokenBudget:
    maximum: int
    used: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def remaining(self) -> int:
        return max(0, self.maximum - self.used)

    async def reserve(self, estimate: int) -> bool:
        """Atomically reserve up to ``estimate`` tokens, or stop at the cap.

        The previous design ran ``can_start()`` (checks ``used < maximum``) and
        then ``consume()`` (adds the real count *after* the call) as two separate
        locked steps.  That lets several concurrent children all observe ``used <
        maximum`` and launch, so the async mode can start a few extra calls past
        the boundary that linear would not.  Here the check-and-reserve happen
        under a single lock, so a call is allowed to start only if its estimated
        cost still fits; the caller settles to the actual count afterwards.
        """
        async with self._lock:
            estimate = max(0, int(estimate))
            if self.used + estimate > self.maximum:
                return False
            self.used += estimate
            return True

    async def settle(self, estimate: int, actual: int) -> None:
        """Release the unspent part of an earlier reservation and charge the truth."""
        async with self._lock:
            self.used -= max(0, int(estimate))
            self.used += max(0, int(actual))


class ChildAgent:
    def __init__(
        self, backend: ModelBackend, workspace: WorkspaceRuntime,
        config: ScaffoldConfig, emitter: ProtocolEmitter,
        token_budget: BudgetPool,
    ) -> None:
        self.backend = backend
        self.workspace = workspace
        self.config = config
        self.emitter = emitter
        self.token_budget = token_budget
        # The reservation of the in-flight turn, so a failure or timeout between
        # reserve and settle can release its provisional charge back to the pool
        # instead of leaking it into ``reserved``.
        self._open_reservation: Reservation | None = None

    @staticmethod
    def tools() -> list[dict[str, Any]]:
        return [
            function_tool("terminal", "Run a command in this child's isolated container.", {
                "command": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
            }, ["command"]),
            function_tool("submit_result", "Seal the child result for the benchmark gateway. This does not modify the main workspace. Evidence must report observed contract facts (for example final recovered row count, profile version, or revision state), not merely expected goals.", {
                "summary": {"type": "string"},
                "result_kind_hint": {"type": "string", "description": "Free-text semantic description, not a benchmark enum."},
                "evidence": {"type": "object", "description": "Observed, machine-checkable facts supporting the semantic hint; do not put expected/target values here as if observed."},
                "files": {"type": "array", "items": {"type": "string"}},
                "patch": {"type": "string"},
            }, ["summary", "result_kind_hint"]),
        ]

    async def release_open_reservation(self) -> None:
        """Release the in-flight reservation if a turn never reached ``settle``.

        A reserved child turn is settled on the normal path.  If the backend call
        raised, or ``asyncio.wait_for`` (child timeout) cancelled the turn before
        settle, the provisional charge stays in ``reserved`` and silently
        compresses every sibling's headroom.  ``_run_child`` calls this in a
        ``finally`` so a failed child returns its estimate immediately.  It is a
        no-op when no reservation is open (the normal case).
        """
        reservation = self._open_reservation
        if reservation is None:
            return
        self._open_reservation = None
        await self.token_budget.release(reservation.reservation_id)
        self.emitter.emit(
            "budget_released",
            pool=self.token_budget.name,
            reservation_id=reservation.reservation_id,
            estimate=reservation.estimated_total,
            remaining=self.token_budget.remaining,
        )

    async def run(
        self, record: ChildRecord, model: str, seed: int,
    ) -> tuple[dict[str, Any], str, int]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": (
                "You are a subagent created by one main agent. Work only on the delegated task in your isolated "
                "container. You cannot communicate with other children and must not assume your changes are visible "
                "to the main agent. Use submit_result with a concise semantic hint, evidence, and any paths that the "
                "main agent may later promote. Before installing tools or assuming an external service is missing, "
                "inspect the delegated workspace for evaluator-staged evidence, scripts, and workstream assets. "
                "Do not claim that files were applied to the main workspace."
            )},
            {"role": "user", "content": json.dumps({
                "delegated_task": record.task,
                "targets": record.targets,
                "expected_output": record.expected_output,
                "required_observed_evidence_fields": record.required_evidence_fields,
                "observed_evidence_schema": record.evidence_schema,
                "allowed_reported_result_files": record.allowed_result_files,
                "required_reported_result_files": record.required_result_files,
                "participant_visible_result_contract": record.public_result_contract,
            }, ensure_ascii=False, sort_keys=True)},
        ]
        total_tokens = 0
        unsealed_turns = 0
        for turn_index in range(1, self.config.max_child_turns + 1):
            role = f"child:{record.child_id}"
            input_bound, accounting_mode = _estimate_input(
                self.backend, messages, self.tools(),
            )
            reservation = await self.token_budget.reserve(
                input_bound, self.config.max_output_tokens,
                accounting_mode=accounting_mode,
            )
            if reservation is None:
                self._open_reservation = None
                self.emitter.emit(
                    "budget_exhausted", pool=self.token_budget.name,
                    role=role, turn=turn_index,
                )
                return {
                    "summary": "episode token budget exhausted before child completion",
                    "evidence": {"token_budget_exhausted": True}, "files": [],
                }, record.expected_output, total_tokens
            # Track the in-flight reservation so failure/timeout cleanup can
            # release it (see ``release_open_reservation``).
            self._open_reservation = reservation
            self.emitter.emit(
                "budget_reserved",
                pool=self.token_budget.name,
                reservation_id=reservation.reservation_id,
                input_upper_bound=input_bound,
                max_output=self.config.max_output_tokens,
                accounting_mode=accounting_mode,
                remaining=self.token_budget.remaining,
            )
            self.emitter.emit(
                "agent_progress", phase="model_call_started", role=role,
                turn=turn_index, model=model,
            )
            turn = await self.backend.complete(
                role=role, model=model, messages=messages,
                tools=self.tools(), seed=_role_seed(seed, record.child_id),
            )
            overrun = await self.token_budget.settle(
                reservation.reservation_id, turn.total_tokens,
            )
            self._open_reservation = None
            self.emitter.emit(
                "budget_settled",
                pool=self.token_budget.name,
                reservation_id=reservation.reservation_id,
                estimate=reservation.estimated_total,
                actual=turn.total_tokens,
                overrun=overrun,
                remaining=self.token_budget.remaining,
                accounting_mode=self.token_budget.accounting_mode,
            )
            self.emitter.emit(
                "agent_progress", phase="model_call_finished", role=role,
                turn=turn_index, tokens=turn.total_tokens,
            )
            emit_runtime_metadata_snapshot(self.backend, self.emitter)
            total_tokens += turn.total_tokens
            if turn_index == 1:
                self.emitter.emit(
                    "child_progress_checkpoint", child_id=record.child_id,
                    phase="first_model_turn_finished", tokens=turn.total_tokens,
                )
            messages.append(turn.assistant_message)
            if not turn.tool_calls:
                unsealed_turns += 1
                if unsealed_turns <= 2:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your delegated workstream has not been sealed. Do not run more commands. "
                            "Call submit_result now with the observed outcome, including failures or "
                            "incomplete work truthfully in summary/evidence."
                        ),
                    })
                    continue
                content = turn.assistant_message.get("content") or "child ended without a structured result"
                return {
                    "summary": str(content),
                    "evidence": {"structured_submission": False, "unsealed_turns": unsealed_turns},
                    "files": [],
                }, record.expected_output, total_tokens
            unsealed_turns = 0
            submitted: tuple[dict[str, Any], str] | None = None
            for call in turn.tool_calls:
                if call.name == "terminal":
                    command = str(call.arguments.get("command", ""))
                    timeout = int(call.arguments.get("timeout_seconds") or self.config.child_terminal_timeout_sec)
                    result = await self.workspace.child_terminal(record.child_id, command, timeout)
                    messages.append(_tool_result(call.id, {
                        "exit_code": result.exit_code,
                        "output": _trim(result.output, self.config.max_tool_output_chars),
                    }))
                elif call.name == "submit_result":
                    evidence = call.arguments.get("evidence") or {}
                    missing_evidence = [
                        field_name for field_name in record.required_evidence_fields
                        if not isinstance(evidence, dict)
                        or evidence.get(field_name) is None
                        or evidence.get(field_name) == ""
                    ]
                    if missing_evidence:
                        messages.append(_tool_result(call.id, {
                            "sealed": False,
                            "error": "missing required observed evidence fields",
                            "missing_evidence_fields": missing_evidence,
                        }))
                        continue
                    files = list(call.arguments.get("files") or [])
                    missing_files = sorted(set(record.required_result_files) - set(files))
                    unexpected_files = sorted(set(files) - set(record.allowed_result_files))
                    if record.result_file_contract_enforced and (missing_files or unexpected_files):
                        messages.append(_tool_result(call.id, {
                            "sealed": False,
                            "error": "reported result files violate the workstream contract",
                            "missing_required_files": missing_files,
                            "unexpected_files": unexpected_files,
                            "allowed_files": record.allowed_result_files,
                        }))
                        continue
                    payload = {
                        "summary": str(call.arguments.get("summary", "")),
                        "evidence": evidence,
                        "files": files,
                    }
                    if call.arguments.get("patch"):
                        payload["patch"] = str(call.arguments["patch"])
                    public_codes, public_details = validate_payload_contract(
                        {
                            "required_evidence_fields": record.required_evidence_fields,
                            "evidence_schema": record.evidence_schema,
                            "allowed_files": (
                                record.allowed_result_files
                                if record.result_file_contract_enforced else files
                            ),
                            "required_files": (
                                record.required_result_files
                                if record.result_file_contract_enforced else []
                            ),
                        },
                        {"payload": payload},
                    )
                    if public_codes:
                        messages.append(_tool_result(call.id, {
                            "sealed": False,
                            "error": "result does not satisfy the participant-visible contract",
                            "reason_codes": public_codes,
                            "details": public_details,
                        }))
                        continue
                    hint = str(call.arguments.get("result_kind_hint", ""))
                    messages.append(_tool_result(call.id, {"sealed": True}))
                    submitted = payload, hint
                else:
                    messages.append(_tool_result(call.id, {"error": f"unknown child tool {call.name}"}))
            if submitted is not None:
                return submitted[0], submitted[1], total_tokens
        return {
            "summary": "child exhausted its turn budget without submit_result",
            "evidence": {"turn_budget_exhausted": True},
            "files": [],
        }, record.expected_output, total_tokens


class SubagentManager:
    def __init__(
        self,
        *,
        start: dict[str, Any],
        backend: ModelBackend,
        workspace: WorkspaceRuntime,
        emitter: ProtocolEmitter,
        config: ScaffoldConfig,
        token_budget: BudgetPool,
    ) -> None:
        self.start = start
        self.backend = backend
        self.workspace = workspace
        self.emitter = emitter
        self.config = config
        self.token_budget = token_budget
        self.children: dict[str, ChildRecord] = {}
        self.completion_to_child: dict[str, str] = {}
        self._delivery_event = asyncio.Event()
        self._counter = 0
        self._completion_counter = 0
        self._start_condition = asyncio.Condition()
        self._started_child_ids: set[str] = set()
        self._initial_barrier_failed = False
        # FIFO presentation queue (spec §5): released deliveries are enqueued in
        # receive order and presented at most one per main-model request, each
        # opening a response window that must settle (or hit max_response_turns)
        # before the next occurrence unseals.
        self.presentation_queue = PresentationQueue()
        self._occurrence_counter = 0

    def unresolved_count(self) -> int:
        return sum(
            record.status not in {"delivered", "cancelled", "rejected", "contract_rejected"}
            for record in self.children.values()
        )

    def active_count(self) -> int:
        return sum(record.status in {"spawned", "starting", "running"} for record in self.children.values())

    def recovery_spawn_count(self) -> int:
        """Count model-requested replacement/recovery children.

        The benchmark-owned initial wave establishes the evaluation scenario;
        it is not a delegation decision made by the evaluated model and must
        not consume the model's bounded recovery-spawn allowance.
        """
        return sum(not record.initial_wave for record in self.children.values())

    def remaining_spawn_budget(self) -> int:
        return max(0, self.config.max_total_child_spawns - self.recovery_spawn_count())

    def _concurrency_limit(self) -> int:
        # The initial wave is benchmark-owned scenario construction, not a
        # participant delegation choice. Admit the complete bounded wave so a
        # case with more workstreams than the participant recovery limit still
        # creates the declared concurrent opportunity. Once it is admitted, later
        # recovery/redelegation children use the participant profile limit.
        # Linear runs the same benchmark-owned wave concurrently — the only
        # difference from async is that the main model is shown ONE atomic bundle
        # at the end instead of per-result asynchronous interruptions.
        initial_records = self._initial_records()
        if any(record.status == "queued" for record in initial_records):
            return max(self.config.max_concurrent_children, len(initial_records))
        return self.config.max_concurrent_children

    def _launch_queued(self) -> None:
        while self.active_count() < self._concurrency_limit():
            record = next((item for item in self.children.values() if item.status == "queued"), None)
            if record is None:
                return
            record.status = "spawned"
            record.asyncio_task = asyncio.create_task(
                self._run_child(record), name=f"async_rbench-{record.child_id}"
            )

    async def _signal_start_progress(self) -> None:
        """Wake siblings blocked in ``_wave_start_barrier`` for a child that just
        left ``starting`` (either to ``running`` or to ``cancelled``)."""
        async with self._start_condition:
            self._start_condition.notify_all()

    def _initial_records(self) -> list[ChildRecord]:
        return [record for record in self.children.values() if record.initial_wave]

    def _initial_wave_started(self) -> bool:
        records = self._initial_records()
        if not records:
            return False
        # A case may declare more initial workstreams than the live concurrency
        # limit. Queued children cannot start until an active child completes,
        # so including them in the start barrier creates a circular wait. The
        # barrier covers the currently admitted cohort; queued work joins a
        # later cohort as slots become available.
        admitted = [record for record in records if record.status != "queued"]
        return bool(admitted) and all(
            record.child_id in self._started_child_ids for record in admitted
        )

    def _initial_wave_failed(self) -> bool:
        return self._initial_barrier_failed or any(
            record.status == "cancelled" and record.child_id not in self._started_child_ids
            for record in self._initial_records()
        )

    # --- Linear atomic sync barrier (spec §6 synchronous aggregation) ---------
    #
    # Linear runs the benchmark-owned wave concurrently but shows the main model
    # exactly ONE immutable bundle at the end, sorted by workstream_id. The
    # barrier counts *terminal* resolution, not successful completion, so a
    # contract rejection, a designed cancellation, or a timeout still closes the
    # slot and enters the bundle as a workstream that did not deliver.

    def _linear_terminal(self, record: ChildRecord) -> bool:
        return record.status in LINEAR_TERMINAL_STATUSES

    def linear_bundle_ready(self) -> bool:
        """True once every benchmark wave child has reached a terminal state."""
        records = list(self.children.values())
        return bool(records) and all(self._linear_terminal(record) for record in records)

    async def _wait_for_linear_terminal(self) -> None:
        while not self.linear_bundle_ready():
            # Re-check after clearing so a terminal transition that fires between
            # the re-check and the wait is never lost.
            self._delivery_event.clear()
            if self.linear_bundle_ready():
                return
            await self._delivery_event.wait()

    async def wait_linear_bundle(self, timeout: float) -> bool:
        """Wait until the whole benchmark wave is terminal (or timeout)."""
        try:
            await asyncio.wait_for(self._wait_for_linear_terminal(), timeout=timeout)
        except asyncio.TimeoutError:
            return self.linear_bundle_ready()
        return self.linear_bundle_ready()

    def build_linear_bundle(self) -> dict[str, Any]:
        """Aggregate the terminal wave into ONE stable, participant-safe bundle.

        The bundle is ordered by workstream_id (stable across runs), carries a
        status per workstream (``delivered``, ``contract_rejected``, or the
        terminal reason), and never exposes evaluator-private event roles — each
        delivery/rejection is projected through ``public_delivery`` /
        ``public_rejection``.
        """
        ordered = sorted(
            list(self.children.values()),
            key=lambda record: (record.work_units[0] if record.work_units else ""),
        )
        return {"workstreams": [self._linear_entry(record) for record in ordered]}

    def _linear_entry(self, record: ChildRecord) -> dict[str, Any]:
        workstream_id = record.work_units[0] if record.work_units else None
        base: dict[str, Any] = {"workstream_id": workstream_id}
        if record.delivery is not None:
            base["status"] = "delivered"
            base["result"] = public_delivery(record.delivery, workstream_id=workstream_id)
        elif record.contract_rejection is not None:
            base["status"] = "contract_rejected"
            base["rejection"] = public_rejection(
                record.contract_rejection, workstream_id=workstream_id,
            )
        elif record.status == "contract_rejected":
            base["status"] = "contract_rejected"
            base["rejection"] = public_rejection(
                {"child_id": record.child_id, "completion_id": record.completion_id},
                workstream_id=workstream_id,
            )
        else:
            base["status"] = record.status
            base["reason"] = record.decision or "no usable result delivered"
        return base

    async def _wait_for_initial_wave_resolution(self) -> None:
        while not self._initial_wave_started() and not self._initial_wave_failed():
            await self._start_condition.wait()

    def _record_initial_barrier_failure(self, detail: str) -> None:
        if self._initial_barrier_failed:
            return
        self._initial_barrier_failed = True
        self.emitter.emit(
            "infrastructure_failure", component="initial_wave_barrier", detail=detail,
        )

    async def wait_initial_wave_ready(self) -> bool:
        """Wait until the benchmark-owned wave is real before the first main call."""
        async with self._start_condition:
            try:
                await asyncio.wait_for(
                    self._wait_for_initial_wave_resolution(),
                    timeout=self.config.start_barrier_timeout_sec,
                )
            except asyncio.TimeoutError:
                self._record_initial_barrier_failure(
                    "initial children did not start within the start barrier timeout"
                )
                self._start_condition.notify_all()
        return self._initial_wave_started() and not self._initial_wave_failed()

    async def _wave_start_barrier(self, record: ChildRecord) -> None:
        """Cluster concurrent ``child_started`` events before any agent loop runs.

        Children admitted together must all leave ``starting`` (emitting
        ``child_started``) before the first one enters its agent loop. Queued
        initial workstreams are deliberately excluded until the concurrency
        controller admits them. Without this, a wave larger than the live
        concurrency limit can never pass the barrier.

        A child that never leaves ``starting`` (for example a workspace
        ``create_child`` that hangs) would block every sibling behind the
        benchmark-owned initial-start barrier. That is an infrastructure
        failure: the concurrent opportunity was not established, so the episode
        must be unscored rather than attributed to model behaviour.
        """
        if not record.initial_wave:
            return
        async with self._start_condition:
            self._start_condition.notify_all()
            try:
                await asyncio.wait_for(
                    self._wait_for_initial_wave_resolution(),
                    timeout=self.config.start_barrier_timeout_sec,
                )
            except asyncio.TimeoutError:
                self._record_initial_barrier_failure(
                    "initial children did not start within the start barrier timeout"
                )
                self._start_condition.notify_all()

    async def spawn(
        self, workstream_id: str, task: str, targets: list[str],
        expected_output: str, priority: str,
    ) -> dict[str, Any]:
        allowed = set(self.start.get("allowed_work_units") or [])
        if workstream_id not in allowed:
            result = {
                "error": f"unknown workstream_id {workstream_id!r}",
                "allowed_workstreams": sorted(allowed),
                "budget_consumed": False,
            }
            self.emitter.emit(
                "delegation_validation_error", requested_workstream=workstream_id,
                reason=result["error"], budget_consumed=False,
            )
            return result
        assigned = {
            unit for record in self.children.values()
            if record.status != "cancelled"
            for unit in record.work_units
        }
        # The first wave is the controlled event bundle. It must cover every
        # workstream exactly once. Later replacement/recovery work may reuse one.
        if assigned != allowed and workstream_id in assigned:
            result = {
                "error": f"initial workstream {workstream_id!r} is already assigned",
                "remaining_workstreams": sorted(allowed - assigned),
                "budget_consumed": False,
            }
            self.emitter.emit(
                "delegation_validation_error", requested_workstream=workstream_id,
                reason=result["error"], budget_consumed=False,
            )
            return result
        if self.recovery_spawn_count() >= self.config.max_total_child_spawns:
            result = {
                "error": f"maximum total child spawns {self.config.max_total_child_spawns} reached",
                "budget_consumed": False,
            }
            self.emitter.emit(
                "delegation_validation_error", requested_workstream=workstream_id,
                reason=result["error"], budget_consumed=False,
            )
            return result
        self._counter += 1
        child_id = f"child-{self._counter}"
        work_units = [workstream_id]
        record = ChildRecord(
            child_id=child_id,
            task=task,
            work_units=work_units,
            targets=targets,
            expected_output=expected_output,
            priority=priority,
            initial_wave=False,
            required_evidence_fields=[
                str(field_name) for field_name in
                (self.start.get("workstream_contracts") or {}).get(workstream_id, {}).get(
                    "required_evidence_fields", []
                )
            ],
            evidence_schema=dict(
                (self.start.get("workstream_contracts") or {}).get(workstream_id, {}).get(
                    "evidence_schema", {}
                )
            ),
            allowed_result_files=[
                str(path) for path in
                (self.start.get("workstream_contracts") or {}).get(workstream_id, {}).get(
                    "allowed_files", []
                )
            ],
            required_result_files=[
                str(path) for path in
                (self.start.get("workstream_contracts") or {}).get(workstream_id, {}).get(
                    "required_files", []
                )
            ],
            public_result_contract=dict(
                (self.start.get("workstream_contracts") or {}).get(workstream_id, {}).get(
                    "public_result_contract", {}
                )
            ),
            result_file_contract_enforced=bool(self.start.get("result_contract_enforced")),
        )
        self.children[child_id] = record
        self.emitter.emit(
            "child_spawned", child_id=child_id, parent_id="main",
            work_units=work_units, initial_wave=False,
        )
        self._launch_queued()
        return {
            "child_id": child_id,
            "status": record.status,
            "workstream_id": workstream_id,
            "remaining_total_spawns": self.remaining_spawn_budget(),
        }

    def spawn_initial_wave(self) -> dict[str, Any]:
        """Benchmark-owned auto-start of the case-declared initial wave.

        The benchmark starts the case's explicit initial concurrent workstreams
        before the first main model API call; the evaluated model is never asked
        to have spawned the initial team. Initial children use the benchmark's
        bounded initial-wave capacity and do not consume the participant's
        replacement/recovery allowance. Each record is tagged
        ``initial_wave=True``. An invalid or unstartable declaration is an
        infrastructure failure, not a model failure.
        """
        wave = self.start.get("initial_wave") or []
        if len(wave) > MAX_INITIAL_WORKSTREAMS:
            detail = (
                "initial_wave exceeds fixed harness limit "
                f"({len(wave)} > {MAX_INITIAL_WORKSTREAMS})"
            )
            self.emitter.emit(
                "infrastructure_failure",
                component="initial_wave_declaration",
                detail=detail,
            )
            return {"error": detail, "budget_consumed": False}
        expected = set(self.start.get("allowed_work_units") or [])
        wave_ids = [str(item.get("workstream_id")) for item in wave]
        if set(wave_ids) != expected or len(wave_ids) != len(set(wave_ids)):
            detail = "initial_wave does not map one-to-one to delegation_workstreams"
            self.emitter.emit("infrastructure_failure", component="initial_wave_declaration", detail=detail)
            return {"error": detail, "budget_consumed": False}
        if self.children:
            detail = "initial wave is already initialized"
            self.emitter.emit("infrastructure_failure", component="initial_wave_budget", detail=detail)
            return {"error": detail, "budget_consumed": False}
        workstream_contracts = self.start.get("workstream_contracts") or {}
        spawned: list[dict[str, Any]] = []
        for item in wave:
            workstream_id = str(item.get("workstream_id"))
            self._counter += 1
            child_id = f"child-{self._counter}"
            record = ChildRecord(
                child_id=child_id,
                task=str(item.get("task", "")),
                work_units=[workstream_id],
                targets=[str(value) for value in item.get("targets") or []],
                expected_output=str(item.get("expected_output", "")),
                priority=str(item.get("priority", "normal")),
                initial_wave=True,
                required_evidence_fields=[
                    str(field_name) for field_name in
                    workstream_contracts.get(workstream_id, {}).get("required_evidence_fields", [])
                ],
                evidence_schema=dict(
                    workstream_contracts.get(workstream_id, {}).get("evidence_schema", {})
                ),
                allowed_result_files=[
                    str(path) for path in
                    workstream_contracts.get(workstream_id, {}).get("allowed_files", [])
                ],
                required_result_files=[
                    str(path) for path in
                    workstream_contracts.get(workstream_id, {}).get("required_files", [])
                ],
                public_result_contract=dict(
                    workstream_contracts.get(workstream_id, {}).get(
                        "public_result_contract", {}
                    )
                ),
                result_file_contract_enforced=bool(self.start.get("result_contract_enforced")),
            )
            self.children[child_id] = record
            self.emitter.emit(
                "child_spawned", child_id=child_id, parent_id="main",
                work_units=[workstream_id], initial_wave=True,
            )
            spawned.append({
                "child_id": child_id, "workstream_id": workstream_id, "status": record.status,
            })
        self._launch_queued()
        return {
            "spawned": spawned,
            "budget_consumed": False,
            "remaining_total_spawns": self.remaining_spawn_budget(),
        }

    async def _run_child(self, record: ChildRecord) -> None:
        record.status = "starting"
        try:
            try:
                await self.workspace.create_child(record.child_id)
            except Exception as exc:
                record.status = "cancelled"
                await self._signal_start_progress()
                detail = f"failed to create isolated child workspace: {exc}"
                self.emitter.emit(
                    "infrastructure_failure", component="child_workspace",
                    child_id=record.child_id, detail=detail,
                )
                self.emitter.emit(
                    "child_cancelled", child_id=record.child_id,
                    reason="infrastructure failure: child workspace could not start",
                    initiated_by="infrastructure",
                )
                self._delivery_event.set()
                LOGGER.exception("child %s workspace creation failed", record.child_id)
                return
            record.status = "running"
            # A started interval now proves that the isolated workspace exists.
            self.emitter.emit("child_started", child_id=record.child_id)
            self._started_child_ids.add(record.child_id)
            await self._signal_start_progress()
            await self._wave_start_barrier(record)
            await asyncio.sleep(0)
            # v2 uses actual child completion timing. No case-specific role is
            # paused inside the participant-facing scaffold to manufacture an
            # arrival order.
            agent = ChildAgent(
                self.backend, self.workspace, self.config, self.emitter,
                self.token_budget,
            )
            try:
                payload, hint, tokens = await asyncio.wait_for(
                    agent.run(
                        record, self.config.child_model, int(self.start["agent_seed"]),
                    ),
                    timeout=self.config.child_timeout_sec,
                )
            finally:
                # A child timeout or a raised backend call must release its
                # provisional charge; a normal completion already settled, so
                # this is a no-op on the success path.
                await agent.release_open_reservation()
            self._completion_counter += 1
            completion_id = f"completion-{self._completion_counter}"
            record.status = "completed_hidden"
            record.completion_id = completion_id
            record.payload = payload
            record.tokens = tokens
            self.completion_to_child[completion_id] = record.child_id
            self.emitter.emit(
                "child_completed",
                child_id=record.child_id,
                completion_id=completion_id,
                payload=payload,
                usage={"tokens": tokens},
            )
        except asyncio.CancelledError:
            record.status = "cancelled"
            raise
        except Exception as exc:
            record.status = "cancelled"
            self.emitter.emit(
                "child_cancelled", child_id=record.child_id,
                reason=f"child failure: {exc}", initiated_by="infrastructure",
            )
            self._delivery_event.set()
            LOGGER.exception("child %s failed", record.child_id)
        finally:
            # A child leaving the wave — however it exits (success, failure, or
            # cancellation while blocked in the start barrier) — must wake any
            # sibling that is waiting for this child to leave ``starting``.
            await self._signal_start_progress()
            self._launch_queued()

    async def handle_delivery(self, delivery: dict[str, Any]) -> None:
        completion_id = str(delivery.get("completion_id", ""))
        child_id = self.completion_to_child.get(completion_id)
        if not child_id:
            LOGGER.error("gateway delivered unknown completion %s", completion_id)
            return
        record = self.children[child_id]
        record.delivery = delivery
        record.status = "delivered"
        record.presented = False
        if self.start.get("execution_mode") == "linear":
            # Linear shows one atomic bundle at wave end. The result is recorded
            # on the child and aggregated there; it is never presented as a
            # per-result asynchronous interruption, so no occurrence is enqueued
            # and no result_available/adapter_queued boundary is emitted.
            self._delivery_event.set()
            return
        # Async: enqueue a single immutable occurrence in adapter receive order.
        # The gateway-release boundary R_i (``result_available``) is emitted before
        # A_i (``adapter_queued``) so EventStore replay sees the occurrence made
        # available before the adapter claims it (spec §3.2/§3.3).
        self._occurrence_counter += 1
        occurrence = DeliveryOccurrence(
            occurrence_id=f"occ-{self._occurrence_counter}",
            completion_id=completion_id,
            payload=public_delivery(
                delivery,
                workstream_id=record.work_units[0] if record.work_units else None,
            ),
            receive_seq=self._occurrence_counter,
            # A benchmark-delivered completion is a scored observation: it ends
            # the main_pre pool on first presentation (spec §7.1).  The reference
            # scaffold reproduces every delivery as a scored occurrence.
            scored=True,
        )
        self.presentation_queue.enqueue(occurrence)
        self.emitter.emit(
            "result_available",
            delivery_occurrence_id=occurrence.occurrence_id,
            completion_id=completion_id,
        )
        self.emitter.emit(
            "adapter_queued",
            delivery_occurrence_id=occurrence.occurrence_id,
            completion_id=completion_id,
        )
        self._delivery_event.set()

    async def handle_rejection(self, rejection: dict[str, Any]) -> None:
        completion_id = str(rejection.get("completion_id", ""))
        child_id = self.completion_to_child.get(completion_id)
        if not child_id:
            LOGGER.error("gateway rejected unknown completion %s", completion_id)
            return
        record = self.children[child_id]
        record.contract_rejection = rejection
        record.status = "contract_rejected"
        record.decision = "rejected_by_gateway"
        self._delivery_event.set()

    def select_presentable(self) -> DeliveryOccurrence | None:
        """Select at most one queued occurrence that may be presented now.

        ``peek_presentable`` enforces FIFO-by-receive-order while sealing the
        head behind an active response window, so a running main request is never
        handed more than one new occurrence.  Selection alone does NOT mark the
        occurrence presented; the caller must call ``mark_presented`` once a real
        main-model request has started.
        """
        return self.presentation_queue.peek_presentable()

    def mark_presented(
        self, occurrence_id: str, *, turn_id: str, window_id: str,
    ) -> None:
        """Bind a prepared occurrence to a real started main-model request.

        Opens the response window and records the public ``result_presented``
        boundary.  Must only be called after the request that carries the
        occurrence has actually started.
        """
        self.presentation_queue.mark_presented(
            occurrence_id, turn_id=turn_id, window_id=window_id,
        )
        occurrence = self.presentation_queue.presented_occurrence(occurrence_id)
        assert occurrence is not None
        self.emitter.emit(
            "result_presented",
            delivery_occurrence_id=occurrence.occurrence_id,
            completion_id=occurrence.completion_id,
            turn_id=turn_id,
            window_id=window_id,
        )

    def presented_scored(self, occurrence_id: str) -> bool:
        """Whether the presentation of ``occurrence_id`` opens a scored phase.

        The first *scored* presentation ends ``main_pre`` (spec §7.1).  A
        delivered result is scored by default (the reference scaffold presents
        every benchmark-delivered completion); replay occurrences are ``scored``
        only when the delivery itself was scored.
        """
        occurrence = self.presentation_queue.presented_occurrence(occurrence_id)
        return bool(occurrence and occurrence.scored)

    def statuses(self) -> list[dict[str, Any]]:
        # Lifecycle + workstream identity only. Held completion payloads stay
        # hidden until the main model explicitly waits for and acknowledges them.
        return [{
            "child_id": record.child_id,
            "workstream_id": record.work_units[0] if record.work_units else None,
            "status": record.status,
            "targets": record.targets,
            "task": record.task[:400],
            "decision": record.decision,
            "contract_rejection_reason_codes": list(
                (record.contract_rejection or {}).get("reason_codes") or []
            ),
        } for record in self.children.values()]

    async def wait(self, child_ids: list[str], timeout: float, return_when: str) -> dict[str, Any]:
        selected = child_ids or list(self.children)

        def ready() -> bool:
            states = [self.children[item].status for item in selected if item in self.children]
            if not states:
                return False
            terminal = {"delivered", "rejected", "contract_rejected", "cancelled"}
            return all(state in terminal for state in states) if return_when == "all" else any(state in terminal for state in states)

        if not ready():
            try:
                await asyncio.wait_for(self._delivery_event.wait(), timeout=max(0.0, timeout))
            except asyncio.TimeoutError:
                pass
        return {"ready": ready(), "children": self.statuses()}

    async def cancel(
        self, child_id: str, reason: str, *, initiated_by: str = "main",
    ) -> dict[str, Any]:
        record = self.children.get(child_id)
        if not record:
            return {"error": f"unknown child {child_id}"}
        if record.status not in {"queued", "spawned", "starting", "running"}:
            return {"error": f"child {child_id} is already {record.status}; reject its delivered result instead"}
        if record.asyncio_task:
            record.asyncio_task.cancel()
            try:
                await record.asyncio_task
            except asyncio.CancelledError:
                pass
        record.status = "cancelled"
        record.decision = "cancelled"
        self.emitter.emit(
            "child_cancelled", child_id=child_id, reason=reason,
            initiated_by=initiated_by,
        )
        await self.workspace.cleanup_child(child_id)
        self._launch_queued()
        return {"child_id": child_id, "status": "cancelled"}

    def acknowledge(self, completion_id: str, decision: str, reason: str, action_id: str) -> dict[str, Any]:
        child_id = self.completion_to_child.get(completion_id)
        if not child_id:
            return {"error": f"unknown completion {completion_id}"}
        record = self.children[child_id]
        if record.delivery is None:
            return {"error": "result has not been delivered by the benchmark gateway"}
        record.decision = decision
        if decision == "use":
            self.emitter.emit("result_consumed", completion_id=completion_id, action_id=action_id)
        elif decision == "reject":
            record.status = "rejected"
        return {
            "completion_id": completion_id,
            "decision": decision,
            "reason": reason,
        }

    def delivered(self, completion_id: str) -> bool:
        child_id = self.completion_to_child.get(completion_id)
        return bool(child_id and self.children[child_id].delivery is not None)

    def accepted(self, completion_id: str) -> bool:
        child_id = self.completion_to_child.get(completion_id)
        return bool(child_id and self.children[child_id].decision == "use")

    def validate_accepted_lineage(self, completion_ids: list[str]) -> str | None:
        undelivered = [item for item in completion_ids if not self.delivered(item)]
        if undelivered:
            return "lineage contains an unknown or undelivered completion: " + ", ".join(undelivered)
        unaccepted = [item for item in completion_ids if not self.accepted(item)]
        if unaccepted:
            return "lineage contains a completion not acknowledged with decision=use: " + ", ".join(unaccepted)
        return None

    def child_for_completion(self, completion_id: str) -> str | None:
        return self.completion_to_child.get(completion_id)

    async def shutdown(self) -> None:
        for record in self.children.values():
            if record.asyncio_task and not record.asyncio_task.done():
                await self.cancel(
                    record.child_id, "episode ended", initiated_by="scaffold_shutdown",
                )
        await self.workspace.cleanup()


class ReferenceScaffold:
    def __init__(
        self,
        *,
        start: dict[str, Any],
        config: ScaffoldConfig,
        backend: ModelBackend,
        workspace: WorkspaceRuntime,
        emitter: ProtocolEmitter,
        delivery_reader: DeliveryReader,
    ) -> None:
        self.start = start
        self.config = config
        self.backend = backend
        self.workspace = workspace
        self.emitter = emitter
        self.delivery_reader = delivery_reader
        # Split token budget pools (spec §7).  Children share one account in
        # every mode; the main side splits into main_pre / main_post for async
        # (phase switch on the first scored presentation) or a single main_total
        # for linear.  Official Track A profiles declare these pool values; the
        # legacy ``max_total_tokens`` ceiling is only a non-official fallback.
        scheme = "linear" if start.get("execution_mode") == "linear" else "async"
        self.budget_ledger = build_budget_ledger(
            scheme,
            child_shared=config.budget_child_shared,
            main_pre=config.budget_main_pre,
            main_post=config.budget_main_post,
            main_total=config.budget_main_total,
        )
        self.token_budget = self.budget_ledger.pool("child_shared")
        self.manager = SubagentManager(
            start=start, backend=backend, workspace=workspace, emitter=emitter,
            config=config, token_budget=self.token_budget,
        )
        self._action_counter = 0
        self._delivery_task: asyncio.Task | None = None
        self.finished = False
        self.finish_status = "incomplete"
        self.final_summary = ""
        self.messages: list[dict[str, Any]] = []
        self.next_turn_index = 1
        self._current_turn_id = ""
        # A newly accepted completion changes the state that the controller is
        # responsible for closing.  Track that logical revision so a commit or
        # verification performed before the acceptance cannot be reused to
        # justify a later completed finish.
        self._accepted_state_revision = 0
        self._final_commit_revision: int | None = None
        self._verification_revision: int | None = None
        self._verification_passed = False

    def main_tools(self) -> list[dict[str, Any]]:
        artifacts = list(self.start.get("allowed_artifacts") or [])
        return [
            function_tool("terminal", "Run a command in the official main case container.", {
                "command": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
            }, ["command"]),
            function_tool("spawn_subagent", "Create one bounded replacement child for a declared benchmark workstream. The benchmark already started the initial wave; an active duplicate workstream is rejected without consuming budget.", {
                "workstream_id": {"type": "string", "enum": list(self.start.get("allowed_work_units") or [])},
                "task": {"type": "string"},
                "targets": {"type": "array", "items": {"type": "string"}},
                "expected_output": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "normal", "high"]},
            }, ["workstream_id", "task", "targets", "expected_output"]),
            function_tool("list_subagents", "Inspect child lifecycle states without revealing held result content.", {}, []),
            function_tool("wait_for_results", "Wait for any or all selected child results. Empty child_ids means all known children.", {
                "child_ids": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 120},
                "return_when": {"type": "string", "enum": ["any", "all"]},
            }, ["child_ids", "timeout_seconds", "return_when"]),
            function_tool("cancel_subagent", "Cancel a running child because its work is no longer useful.", {
                "child_id": {"type": "string"}, "reason": {"type": "string"},
            }, ["child_id", "reason"]),
            function_tool("acknowledge_result", "Explicitly use, reject, or defer a gateway-delivered completion.", {
                "completion_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["use", "reject", "defer"]},
                "reason": {"type": "string"},
            }, ["completion_id", "decision", "reason"]),
            function_tool("promote_child_path", "Copy a path from an accepted child's isolated container into the official main container.", {
                "completion_id": {"type": "string"},
                "source_path": {"type": "string"},
                "destination_path": {"type": "string"},
            }, ["completion_id", "source_path", "destination_path"]),
            function_tool("commit_artifact", "Declare a versioned artifact and the delivered completions previously acknowledged with decision=use in its lineage.", {
                "artifact_id": {"type": "string", "enum": artifacts},
                "version": {"type": "string"},
                "lineage_completion_ids": {"type": "array", "items": {"type": "string"}},
                "evidence_paths": {"type": "array", "items": {"type": "string"}},
                "final": {"type": "boolean"},
            }, ["artifact_id", "version", "lineage_completion_ids"]),
            function_tool("verify_current_state", "Ask the evaluator to run its hidden frozen checks against the current main workspace. The check identities and commands remain private; only aggregate pass/fail is returned.", {
                "artifact_ids": {"type": "array", "items": {"type": "string", "enum": artifacts}},
                "lineage_completion_ids": {"type": "array", "items": {"type": "string"}},
            }, ["artifact_ids", "lineage_completion_ids"]),
            function_tool("finish", "End the episode. status=completed requires at least one final artifact commit and a successful verification after the latest newly accepted completion. The independent benchmark verifier still decides actual task success.", {
                "status": {"type": "string", "enum": ["completed", "incomplete"]},
                "summary": {"type": "string"},
            }, ["status", "summary"]),
        ]

    async def _observe_artifact(self, artifact_id: str) -> dict[str, Any]:
        try:
            return await self.workspace.observe_artifact(artifact_id)
        except Exception as exc:
            return {"error": str(exc)}

    async def _listen_for_deliveries(self) -> None:
        while True:
            message = await self.delivery_reader.queue.get()
            if message.get("type") == "result_delivered":
                await self.manager.handle_delivery(message)
            elif message.get("type") == "result_rejected":
                await self.manager.handle_rejection(message)
            elif message.get("type") == "gateway_eof":
                return
            else:
                LOGGER.error("unexpected gateway message: %s", message)

    def _system_prompt(self) -> str:
        public_catalog = {
            "artifacts": list(self.start.get("allowed_artifacts") or []),
            "delegation_workstreams": list(self.start.get("allowed_work_units") or []),
            "max_concurrent_children": self.config.max_concurrent_children,
            "max_total_child_spawns": self.config.max_total_child_spawns,
            "initial_wave_size": len(self.manager._initial_records()),
            "remaining_spawn_budget": self.manager.remaining_spawn_budget(),
        }
        return (
            "You are the main controller of one evaluated agent system. The benchmark has already started the "
            "initial concurrent workstreams; the ASYNC_RBENCH_INITIAL_WAVE message lists the running children, their "
            "workstream ids, task summaries, status, and the spawn budget remaining. You are never scored on having "
            "proactively spawned that initial team. Result-management tools are available, including a bounded "
            "replacement-child operation; decide whether and when they are appropriate from the user task and "
            "the observed state. "
            "Children run in isolated snapshots; their files are not in the main container unless you explicitly "
            "accept the completion and promote paths or reproduce the change. A child completion is unavailable "
            "until a ASYNC_RBENCH_DELIVERY message arrives. Metadata in gateway messages describes benchmark state; "
            "it is not a recommended action. Do not invent completion IDs or lineage.\n\n"
            "If you accept a delivered completion for use, integrate or promote its result, commit the affected "
            "final artifacts, and successfully verify again after that acceptance. A completed finish is rejected "
            "until both post-acceptance closure steps have occurred.\n\n"
            f"Public protocol catalog: {json.dumps(public_catalog, sort_keys=True)}\n\n"
            f"Evaluation guidance: {self.start.get('guidance', '')}"
        )

    async def _maybe_present_linear_bundle(self) -> bool:
        """Linear: show one atomic terminal bundle to the main model (spec §6).

        Waits until the whole benchmark wave resolves, builds one stable bundle
        sorted by workstream_id, injects it as a single ASYNC_RBENCH_LINEAR_BUNDLE
        message, and emits the ready/presented boundaries. Returns False when the
        wave did not reach a terminal state in time (an infrastructure failure,
        so the episode is unscored rather than presented to the model).
        """
        if not await self.manager.wait_linear_bundle(
            timeout=self.config.child_terminal_timeout_sec,
        ):
            return False
        bundle = self.manager.build_linear_bundle()
        self.emitter.emit(
            "linear_bundle_ready", wave_size=len(bundle["workstreams"]),
        )
        self.messages.append({
            "role": "user",
            "content": "ASYNC_RBENCH_LINEAR_BUNDLE " + json.dumps(
                bundle, ensure_ascii=False, sort_keys=True,
            ),
        })
        self.emitter.emit(
            "linear_bundle_presented",
            wave_size=len(bundle["workstreams"]),
            workstream_ids=[item["workstream_id"] for item in bundle["workstreams"]],
        )
        return True

    def _on_result_presented(self, occurrence_id: str) -> None:
        """Flip the main pool to ``main_post`` on the first scored presentation.

        Spec §7.1: the async main side has a ``main_pre`` account that is live
        only until the first valid scored ``result_presented``; afterwards main
        calls charge ``main_post``.  The switch is explicit and happens exactly
        once.  A presentation whose occurrence is not scored (replay of an
        unscored delivery) must not advance the phase.
        """
        if not self.manager.presented_scored(occurrence_id):
            return
        if self.budget_ledger.main_phase == "pre":
            self.budget_ledger.switch_to_post()
            self.emitter.emit(
                "budget_phase_switch",
                phase="main_post",
                triggered_by_occurrence=occurrence_id,
            )

    def _close_presentation_window(self) -> None:
        """Close the active response window and emit the S_i^+ closure boundary.

        A presented occurrence opens a ``ResponseWindow``; once it settles or
        hits ``max_response_turns`` it closes, which must be recorded as the
        ``response_window_closed`` boundary so EventStore replay can reconstruct
        the closed window (spec §3.3). The ``delivery_occurrence_id`` links the
        closure back to the occurrence that opened it.
        """
        window = self.manager.presentation_queue.active_window
        if not self.manager.presentation_queue.close_active_window():
            return
        if window is not None:
            self.emitter.emit(
                "response_window_closed",
                window_id=window.window_id,
                delivery_occurrence_id=window.occurrence_id,
                completed_turns=window.completed_turns,
            )

    async def run(self) -> None:
        self.delivery_reader.start()
        self._delivery_task = asyncio.create_task(
            self._listen_for_deliveries(), name="async_rbench-delivery-listener",
        )
        if not self.messages:
            # The benchmark owns the initial concurrent wave: start it before the
            # first main model API call so the model inherits already-running,
            # benchmark-declared workstreams.
            wave = self.manager.spawn_initial_wave()
            if wave.get("error"):
                self.finish_status = "incomplete"
                self.final_summary = f"initial wave could not start: {wave['error']}"
                return
            if not await self.manager.wait_initial_wave_ready():
                self.finish_status = "incomplete"
                self.final_summary = "initial wave did not reach the benchmark start barrier"
                return
            self.messages = [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": str(self.start["instruction"])},
            ]
            if self.start.get("execution_mode") == "linear":
                if not await self._maybe_present_linear_bundle():
                    self.finish_status = "incomplete"
                    self.final_summary = "linear initial wave did not reach a terminal bundle"
                    return
            # Environment snapshot: the benchmark-started wave is already running,
            # along with the concurrency limit and the spawn budget remaining for
            # recovery redelegation. This is the model's only initial state view.
            self.messages.append({
                "role": "user",
                "content": "ASYNC_RBENCH_INITIAL_WAVE " + json.dumps({
                    "started_workstreams": self.manager.statuses(),
                    "max_concurrent_children": self.config.max_concurrent_children,
                    "max_total_child_spawns": self.config.max_total_child_spawns,
                    "initial_wave_size": len(self.manager._initial_records()),
                    "remaining_spawn_budget": self.manager.remaining_spawn_budget(),
                }, ensure_ascii=False, sort_keys=True),
            })
        messages = self.messages
        idle_turns = 0
        for turn_index in range(self.next_turn_index, self.config.max_main_turns + 1):
            self.next_turn_index = turn_index
            # Track the per-turn reservation so a backend failure (the call
            # raised before settle) releases its provisional charge instead of
            # leaking it into the pool's ``reserved``.
            main_pool: BudgetPool | None = None
            reservation: Reservation | None = None
            settled = False
            try:
                # Reserve the per-call ceiling before launching (under the budget
                # lock), then settle to the true token count on completion.  This
                # keeps the cap a hard ceiling that concurrent main/child calls
                # cannot overrun at the boundary.  Strict conservative admission:
                # estimated_input_upper_bound + requested_max_output <= remaining
                # (spec §7.3).  If the pool has not yet seen a scored presentation,
                # this is the main_pre account; it flips to main_post on the first
                # scored result_presented (spec §7.1).
                main_pool = self.budget_ledger.main_pool()
                input_bound, accounting_mode = _estimate_input(
                    self.backend, messages, self.main_tools(),
                )
                reservation = await main_pool.reserve(
                    input_bound, self.config.max_output_tokens,
                    accounting_mode=accounting_mode,
                )
                if reservation is None:
                    self.finish_status = "budget_exhausted"
                    self.final_summary = "episode token budget exhausted"
                    return
                self.emitter.emit(
                    "budget_reserved",
                    pool=main_pool.name,
                    reservation_id=reservation.reservation_id,
                    input_upper_bound=input_bound,
                    max_output=self.config.max_output_tokens,
                    accounting_mode=accounting_mode,
                    remaining=main_pool.remaining,
                )
                # Budget admission succeeded.  Presentation preparation: select at
                # most one new occurrence in FIFO receive order, but only while no
                # response window is open — never more than one new occurrence per
                # main-model request.  The occurrence enters the request context
                # but is NOT yet marked presented.  It is only appended after the
                # evaluator prepares the before-presentation snapshot S_i^- and
                # authorizes presenting it (spec §3.3, §5.1(4)); on a failed
                # snapshot the occurrence stays queued for a later request.
                candidate = self.manager.select_presentable()
                prepared_occurrence_id: str | None = None
                if candidate is not None:
                    prepared_occurrence_id = await self._prepare_presentation(
                        candidate, f"t{turn_index}",
                    )
                    if prepared_occurrence_id is not None:
                        messages.append({
                            "role": "user",
                            "content": "ASYNC_RBENCH_DELIVERY " + json.dumps(
                                candidate.payload, ensure_ascii=False, sort_keys=True,
                            ),
                        })
                self.emitter.emit(
                    "agent_progress", phase="model_call_started", role="main",
                    turn=turn_index, model=self.config.main_model,
                )
                turn = await self.backend.complete(
                    role="main",
                    model=self.config.main_model,
                    messages=messages,
                    tools=self.main_tools(),
                    seed=_role_seed(int(self.start["agent_seed"]), "main"),
                )
                # The prepared occurrence was injected into the main request that
                # has now actually started and returned (complete() succeeded), so
                # it is observably presented into that request and its response
                # window opens.  mark_presented is intentionally called here, after
                # the await returns, not before the request was issued.
                if prepared_occurrence_id is not None:
                    self.manager.mark_presented(
                        prepared_occurrence_id,
                        turn_id=f"t{turn_index}",
                        window_id=f"w{turn_index}",
                    )
                    # A scored presentation ends main_pre (spec §7.1).  This must
                    # run after the occurrence is presented into a real request.
                    self._on_result_presented(prepared_occurrence_id)
                overrun = await main_pool.settle(
                    reservation.reservation_id, turn.total_tokens,
                )
                settled = True
                self.emitter.emit(
                    "budget_settled",
                    pool=main_pool.name,
                    reservation_id=reservation.reservation_id,
                    estimate=reservation.estimated_total,
                    actual=turn.total_tokens,
                    overrun=overrun,
                    remaining=main_pool.remaining,
                    accounting_mode=main_pool.accounting_mode,
                )
                self.emitter.emit(
                    "agent_progress", phase="model_call_finished", role="main",
                    turn=turn_index, tokens=turn.total_tokens,
                )
                emit_runtime_metadata_snapshot(self.backend, self.emitter)
            except Exception as exc:
                if main_pool is not None and reservation is not None and not settled:
                    await main_pool.release(reservation.reservation_id)
                    self.emitter.emit(
                        "budget_released",
                        pool=main_pool.name,
                        reservation_id=reservation.reservation_id,
                        estimate=reservation.estimated_total,
                        remaining=main_pool.remaining,
                    )
                LOGGER.exception("main model call failed")
                # A raised model API request is benchmark tooling failing, not a
                # decision the participant made (the participant did not choose to
                # stop; the call never returned).  Mark it unscored as an
                # infrastructure crash rather than an X=0, so an API outage mid
                # episode is never counted against the model.  The participant
                # who produced no tool calls (idle_turns) is handled separately
                # and stays a scored X=0.
                self.emitter.emit(
                    "infrastructure_failure",
                    component="model_request", detail=f"main model call failed: {exc}",
                )
                self.finish_status = "incomplete"
                self.final_summary = f"main model failure: {exc}"
                return
            messages.append(turn.assistant_message)
            # The active response window, if any, has now received a main-model
            # response.  Record it, then close the window once it settles (unknown
            # to the adapter) or hits max_response_turns, so the next queued
            # occurrence can unseal on a later request.
            self.manager.presentation_queue.record_turn()
            self._close_presentation_window()
            if (
                not self.manager.presentation_queue.has_pending()
                and self.manager.presentation_queue.active_window is None
            ):
                # Nothing left to present and no window open: a later wait() for a
                # still-running child must block until a fresh delivery arrives.
                self.manager._delivery_event.clear()
            if not turn.tool_calls:
                idle_turns += 1
                if idle_turns >= 2:
                    self.finish_status = "incomplete"
                    self.final_summary = str(turn.assistant_message.get("content") or "main ended without finish")
                    return
                messages.append({"role": "user", "content": "Use a tool to continue, or call finish explicitly."})
                continue
            idle_turns = 0
            self._current_turn_id = f"t{turn_index}"
            for call in turn.tool_calls:
                result = await self._execute_main_tool(call)
                messages.append(_tool_result(call.id, result))
            # The runtime signals that every tool in this assistant response has
            # finished (spec §3.3).  It is a *completion* boundary — not a
            # submission boundary — so the evaluator can observe the state after
            # the whole batch, not after a single isolated tool.
            self.emitter.emit(
                "main_turn_completed",
                turn_id=f"t{turn_index}",
                tool_count=len(turn.tool_calls),
            )
            await asyncio.sleep(0)
            self.next_turn_index = turn_index + 1
            if self.finished:
                return
        self.finish_status = "budget_exhausted"
        self.final_summary = "main turn budget exhausted"

    async def _execute_main_tool(self, call: ToolCall) -> dict[str, Any]:
        args = call.arguments
        if "_malformed_arguments" in args:
            return {"error": "malformed JSON tool arguments", "raw": args["_malformed_arguments"]}
        action_id: str | None = None
        if call.name != "spawn_subagent":
            self._action_counter += 1
            action_id = f"main-action-{self._action_counter}"
            metadata = {"tool": call.name}
            if call.name == "terminal":
                metadata["command"] = str(args.get("command", ""))[:2000]
            elif call.name == "promote_child_path":
                # Record the requested transfer before execution so a failed or
                # rejected promotion remains attributable to the exact child
                # completion and paths in the public trajectory.
                metadata.update({
                    "completion_id": str(args.get("completion_id", "")),
                    "source_path": str(args.get("source_path", "")),
                    "destination_path": str(args.get("destination_path", "")),
                })
            elif call.name == "acknowledge_result":
                metadata.update({
                    "completion_id": str(args.get("completion_id", "")),
                    "decision": str(args.get("decision", "defer")),
                })
            elif call.name == "commit_artifact":
                metadata.update({
                    "artifact_id": str(args.get("artifact_id", "")),
                    "version": str(args.get("version", "")),
                    "lineage_completion_ids": [
                        str(item) for item in args.get("lineage_completion_ids") or []
                    ],
                    "final": bool(args.get("final", False)),
                })
            elif call.name == "verify_current_state":
                metadata.update({
                    "artifact_ids": [str(item) for item in args.get("artifact_ids") or []],
                    "lineage_completion_ids": [
                        str(item) for item in args.get("lineage_completion_ids") or []
                    ],
                })
            self.emitter.emit(
                "main_action_started", action_id=action_id, kind=call.name,
                turn_id=self._current_turn_id,
            )
            await asyncio.sleep(0)
            self.emitter.emit("main_action", action_id=action_id, kind=call.name, **metadata)
            await asyncio.sleep(0)
        try:
            result = await self._dispatch_main_tool(call, args, action_id)
        except Exception as exc:
            LOGGER.exception("main tool %s failed", call.name)
            # ``main_action_finished`` is emitted in a finally-safe error path so
            # an exception still closes the boundary begun by ``main_action_started``.
            await self._finish_main_tool(
                action_id, call.name, success=False, error=str(exc),
            )
            return {"error": str(exc), "tool": call.name}
        await self._finish_main_tool(action_id, call.name, success=True, result=result)
        return result

    async def _dispatch_main_tool(
        self, call: ToolCall, args: dict[str, Any], action_id: str | None,
    ) -> dict[str, Any]:
        """Execute one main tool call and return its result dict.

        Every branch returns from this helper; ``_execute_main_tool`` wraps it so
        ``main_action_started``/``main_action_finished`` bracket exactly one tool
        execution and the post-tool observer sees only the finished boundary.
        """
        if call.name == "terminal":
            result = await self.workspace.main_terminal(
                str(args.get("command", "")),
                int(args.get("timeout_seconds") or self.config.main_terminal_timeout_sec),
            )
            return self._command_payload(result)
        if call.name == "spawn_subagent":
            return await self.manager.spawn(
                str(args.get("workstream_id", "")),
                str(args.get("task", "")),
                [str(item) for item in args.get("targets") or []],
                str(args.get("expected_output", "")),
                str(args.get("priority", "normal")),
            )
        if call.name == "list_subagents":
            return {"children": self.manager.statuses()}
        if call.name == "wait_for_results":
            return await self.manager.wait(
                [str(item) for item in args.get("child_ids") or []],
                float(args.get("timeout_seconds") or 0),
                str(args.get("return_when", "any")),
            )
        if call.name == "cancel_subagent":
            return await self.manager.cancel(str(args.get("child_id", "")), str(args.get("reason", "")))
        if call.name == "acknowledge_result":
            assert action_id is not None
            decision = str(args.get("decision", "defer"))
            if decision not in {"use", "reject", "defer"}:
                return {"error": f"invalid decision {decision}"}
            completion_id = str(args.get("completion_id", ""))
            was_accepted = self.manager.accepted(completion_id)
            result = self.manager.acknowledge(
                completion_id, decision, str(args.get("reason", "")), action_id
            )
            if not result.get("error") and decision == "use" and not was_accepted:
                self._accepted_state_revision += 1
                self._verification_passed = False
            return result
        if call.name == "promote_child_path":
            completion_id = str(args.get("completion_id", ""))
            source_path = str(args.get("source_path", ""))
            destination_path = str(args.get("destination_path", ""))
            assert action_id is not None
            if not self.manager.accepted(completion_id):
                self.emitter.emit(
                    "child_path_promotion_result",
                    action_id=action_id, completion_id=completion_id, child_id=None,
                    source_path=source_path, destination_path=destination_path,
                    success=False, exit_code=None,
                    failure_detail=(
                        "completion must be delivered and acknowledged with decision=use"
                    ),
                )
                return {"error": "completion must be delivered and acknowledged with decision=use before promotion"}
            child_id = self.manager.child_for_completion(completion_id)
            assert child_id is not None
            try:
                result = await self.workspace.promote(
                    child_id, source_path, destination_path
                )
            except Exception as exc:
                self.emitter.emit(
                    "child_path_promotion_result",
                    action_id=action_id, completion_id=completion_id, child_id=child_id,
                    source_path=source_path, destination_path=destination_path,
                    success=False, exit_code=None, failure_detail=str(exc)[:1000],
                )
                raise
            self.emitter.emit(
                "child_path_promotion_result",
                action_id=action_id, completion_id=completion_id, child_id=child_id,
                source_path=source_path, destination_path=destination_path,
                success=result.exit_code == 0, exit_code=result.exit_code,
                failure_detail=(
                    "" if result.exit_code == 0 else _trim(result.output, 1000)
                ),
            )
            return self._command_payload(result)
        if call.name == "commit_artifact":
            lineage = [str(item) for item in args.get("lineage_completion_ids") or []]
            lineage_error = self.manager.validate_accepted_lineage(lineage)
            if lineage_error:
                return {"error": "artifact " + lineage_error}
            artifact_id = str(args.get("artifact_id", ""))
            if artifact_id not in self.start.get("allowed_artifacts", []):
                return {"error": f"unknown artifact {artifact_id}"}
            observation = await self._observe_artifact(artifact_id)
            if observation.get("error"):
                return observation
            self.emitter.emit(
                "artifact_committed",
                artifact_id=artifact_id,
                version=str(args.get("version", "")),
                lineage_completion_ids=lineage,
                evidence_paths=[str(item) for item in args.get("evidence_paths") or []],
                final=bool(args.get("final", False)),
                observed_digest=observation["observed_digest"],
                observed_path=observation["observed_path"],
                evaluator_observed=True,
            )
            if bool(args.get("final", False)):
                self._final_commit_revision = self._accepted_state_revision
            return {
                "committed": True, "artifact_id": artifact_id,
                "observed_digest": observation["observed_digest"],
            }
        if call.name == "verify_current_state":
            lineage = [str(item) for item in args.get("lineage_completion_ids") or []]
            lineage_error = self.manager.validate_accepted_lineage(lineage)
            if lineage_error:
                return {"error": "verification " + lineage_error}
            artifact_ids = [str(item) for item in args.get("artifact_ids") or []]
            if not set(artifact_ids).issubset(self.start.get("allowed_artifacts", [])):
                return {"error": "verification references an unknown artifact"}
            result = await self.workspace.verify_current_state(artifact_ids, lineage)
            self._verification_revision = self._accepted_state_revision
            self._verification_passed = bool(result.get("passed", False))
            return result
        if call.name == "finish":
            requested_status = str(args.get("status", "incomplete"))
            # Finish guard (spec §5.1(6), §9.4): a finish — whether completed
            # or incomplete — must not skip a required occurrence that is
            # queued (adapter-received but unpresented) or an active, unclosed
            # response window.  The guard deliberately does NOT depend on the
            # declared status, so a participant cannot silently surrender past
            # a queued delivery that never reached a main-model request.
            pending_occs = self.manager.presentation_queue.has_pending()
            open_window = (
                self.manager.presentation_queue.active_window is not None
                and self.manager.presentation_queue.active_window.active
            )
            missing: list[str] = []
            if requested_status == "completed":
                if self._final_commit_revision != self._accepted_state_revision:
                    missing.append("a final artifact commit after the latest accepted completion")
                if (
                    self._verification_revision != self._accepted_state_revision
                    or not self._verification_passed
                ):
                    missing.append("a successful verification after the latest accepted completion")
            if pending_occs or open_window:
                missing.append(
                    "all delivered occurrences presented and response windows closed"
                )
            if missing:
                return {
                    "error": "completion_preconditions_not_met",
                    "missing": missing,
                    "accepted_state_revision": self._accepted_state_revision,
                }
            self.finished = True
            self.finish_status = requested_status
            self.final_summary = str(args.get("summary", ""))
            return {"ending": True, "status": self.finish_status}
        return {"error": f"unknown main tool {call.name}"}

    async def _finish_main_tool(
        self, action_id: str | None, kind: str, *, success: bool,
        result: dict[str, Any] | None = None, error: str | None = None,
    ) -> None:
        """Close the ``main_action`` boundary begun before a tool ran.

        Emits ``main_action_finished`` (success/error category + result digest)
        and, for the modifying tools whose completion can establish a
        provisional boundary, hands the finished action to the post-tool observer.
        """
        if action_id is None:
            return
        self.emitter.emit(
            "main_action_finished",
            action_id=action_id, kind=kind, success=success,
            error_category="exception" if not success else None,
            result_digest=self._tool_result_digest(result),
            exit_code=self._tool_exit_code(result),
        )
        await asyncio.sleep(0)
        if success and kind in OBSERVED_TOOLS:
            await self._observe_main_state(kind, action_id)

    @staticmethod
    def _tool_result_digest(result: dict[str, Any] | None) -> str | None:
        if result is None:
            return None
        try:
            return hashlib.sha256(
                json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _tool_exit_code(result: dict[str, Any] | None) -> int | None:
        if not isinstance(result, dict):
            return None
        code = result.get("exit_code")
        if isinstance(code, bool) or not isinstance(code, (int, float)):
            return None
        return int(code)

    async def _observe_main_state(self, kind: str, action_id: str) -> None:
        """Ask the kernel to observe the main workspace for the finished tool."""
        try:
            await self.workspace.observe_main_state(
                reason=f"tool_completed:{kind}",
                action_id=action_id,
                turn_id=self._current_turn_id,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("observe_main_state failed for %s", action_id)

    async def _prepare_presentation(
        self, occurrence: DeliveryOccurrence, turn_id: str,
    ) -> str | None:
        """Authorize presenting one occurrence via the evaluator's S^- snapshot.

        Returns the occurrence id when the kernel prepared the before-snapshot
        and authorized presenting it. Returns None when the snapshot failed, in
        which case the occurrence stays queued and is never marked presented
        (spec §3.3, §5.1(4)).
        """
        try:
            prepared = await self.workspace.prepare_result_presentation(
                occurrence.occurrence_id, turn_id=turn_id,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception(
                "presentation preparation failed for %s", occurrence.occurrence_id,
            )
            return None
        if not (prepared or {}).get("prepared"):
            LOGGER.error(
                "presentation preparation rejected for %s", occurrence.occurrence_id,
            )
            return None
        return occurrence.occurrence_id

    def _command_payload(self, result: CommandResult) -> dict[str, Any]:
        return {"exit_code": result.exit_code, "output": _trim(result.output, self.config.max_tool_output_chars)}

    async def shutdown(self) -> None:
        await self.manager.shutdown()
        if self._delivery_task and not self._delivery_task.done():
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass
