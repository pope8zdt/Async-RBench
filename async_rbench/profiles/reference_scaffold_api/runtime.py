from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import shlex
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from ...evaluation.case_contract import (
    MAX_INITIAL_WORKSTREAMS, PUBLIC_RESULT_REJECTION_CODES,
    contract_part_for_codes, public_delivery, public_rejection,
)
from ...evaluation.public_result_validation import validate_public_submission
from ...evaluation.result_contract import ResultContractValidation
from ...evaluation.presentation import DeliveryOccurrence, PresentationQueue
from ...evaluation.protocol import canonical_digest
from ...evaluation.termination import is_runtime_terminal
from ...evaluation.token_usage import TokenUsageLedger

from .config import ScaffoldConfig
from .gateway import DeliveryReader, ProtocolEmitter
from ...evaluation.model_backend import (
    ModelBackend, ModelTurn, ToolCall,
    function_tool, serialized_conversation_bytes,
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


# Child system prompt. A single mode-free constant: the Linear/Async pairing
# must expose an identical child to both arms (P1-16), so this prompt may not
# reference either arm's execution vocabulary --- only the /app-preference
# exploration guidance and the public self-check tool.
CHILD_SYSTEM_PROMPT = (
    "You are a subagent created by one main agent. Work only on the delegated task in your isolated "
    "container. You cannot communicate with other children and must not assume your changes are visible "
    "to the main agent. Use submit_result with a concise semantic hint, evidence, and any paths that the "
    "main agent may later promote. Before installing tools or assuming an external service is missing, "
    "inspect the delegated workspace for evaluator-staged evidence, scripts, and workstream assets. "
    "Do not claim that files were applied to the main workspace. "
    "Exploration discipline: prefer inspecting the delegated workspace and the files listed in your "
    "instructions (typically /app) --- only broaden to the whole container when the task genuinely "
    "requires it. This is guidance, not a restriction: if the task can only be resolved by looking "
    "wider, do so. Only report files you actually produced at the declared paths. "
    "If your instructions declare a report artifact, write it as valid JSON at the declared path "
    "containing at least the listed fields equal to the evidence you submit, and run validate_result "
    "before submit_result to dry-run the public accept rule."
)


# Modifying tools whose *completion* can establish a provisional boundary. Only
# these are handed to the post-tool observer (spec §4.1(1)); read/query tools and
# the participant-visible ``commit_artifact`` audit signal are deliberately
# excluded so a commit cannot itself create the only scored opportunity (§4.3).
OBSERVED_TOOLS = frozenset({"terminal", "promote_child_path"})

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
    # P0-8: the attempt ordinal (1 = first) and the last rejection feedback a
    # replacement child carries, so the new worker repairs the right part.
    attempt_number: int = 1
    prior_attempt_rejection: dict[str, Any] | None = None
@dataclass(frozen=True)
class ChildRunOutcome:
    kind: Literal[
        "submitted",
        "step_limit_reached",
        "resource_safety_abort",
        "no_submission",
    ]
    payload: dict[str, Any] | None
    hint: str | None
    tokens: int
    reason: str | None = None


class ChildContextBudgetError(RuntimeError):
    """The protocol-preserving child history cannot fit the configured bound."""


class ChildPublicContractDefinitionError(RuntimeError):
    """An in-memory case bypassed strict loading with an invalid public rule."""


def child_record_contract(record: ChildRecord) -> dict[str, Any]:
    return {
        "required_evidence_fields": list(record.required_evidence_fields),
        "evidence_schema": dict(record.evidence_schema),
        "allowed_files": list(record.allowed_result_files),
        "required_files": list(record.required_result_files),
        "public_result_contract": dict(record.public_result_contract),
    }


def compress_child_messages(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    budget_bytes: int,
    keep_recent_blocks: int,
    excerpt_chars: int,
) -> list[dict[str, Any]]:
    """Bound full serialized history without breaking tool-call pairing.

    Only assistant reasoning and tool-result content are lossy. Tool call ids,
    arguments, message order, and the initial system/user contract remain exact;
    if those non-truncatable fields alone exceed the bound, the caller receives
    a typed infrastructure error instead of sending a different payload from the
    one admitted by the token estimator.
    """
    budget_bytes = int(budget_bytes)
    keep_recent_blocks = max(0, int(keep_recent_blocks))
    excerpt_chars = max(0, int(excerpt_chars))
    if serialized_conversation_bytes(messages, tools) <= budget_bytes:
        return messages

    result = list(messages)
    cloned: set[int] = set()
    block = -1
    fields: list[tuple[int, str, int]] = []
    for index, message in enumerate(messages):
        if message.get("role") == "assistant":
            block += 1
            if isinstance(message.get("reasoning_content"), str):
                fields.append((index, "reasoning_content", block))
        elif message.get("role") == "tool" and isinstance(message.get("content"), str):
            fields.append((index, "content", max(block, 0)))

    block_count = block + 1
    recent_from = max(0, block_count - keep_recent_blocks)
    old = [item for item in fields if item[2] < recent_from]
    recent = [item for item in fields if item[2] >= recent_from]

    def replace(index: int, field: str, value: str) -> None:
        if index not in cloned:
            result[index] = dict(result[index])
            cloned.add(index)
        result[index][field] = value

    def excerpt_pass(targets: list[tuple[int, str, int]]) -> bool:
        for index, field, _ in targets:
            value = str(result[index].get(field) or "")
            if len(value) <= excerpt_chars:
                continue
            dropped = len(value) - excerpt_chars
            replace(
                index,
                field,
                value[:excerpt_chars] + f"\n...[compressed {dropped} chars]",
            )
            if serialized_conversation_bytes(result, tools) <= budget_bytes:
                return True
        return False

    if excerpt_pass(old) or excerpt_pass(recent):
        return result

    # If excerpts across many blocks still exceed the hard bound, remove those
    # lossy fields from oldest to newest. Pair identity and arguments stay exact.
    for index, field, _ in [*old, *recent]:
        if result[index].get(field):
            replace(index, field, "")
            if serialized_conversation_bytes(result, tools) <= budget_bytes:
                return result

    raise ChildContextBudgetError(
        "child system/user contract and tool-call history exceed "
        f"the {budget_bytes}-byte context budget"
    )


def build_child_user_message(record: ChildRecord) -> dict[str, Any]:
    """The participant-visible child instruction block.

    P0-8: a replacement child carries the failed-attempt count and the last
    public rejection feedback (reason codes + the contract part to repair), so
    the new worker fixes the right part instead of repeating the defect.
    """
    message: dict[str, Any] = {
        "delegated_task": record.task,
        "targets": record.targets,
        "expected_output": record.expected_output,
        "required_observed_evidence_fields": record.required_evidence_fields,
        "observed_evidence_schema": record.evidence_schema,
        "allowed_reported_result_files": record.allowed_result_files,
        "required_reported_result_files": record.required_result_files,
        "participant_visible_result_contract": record.public_result_contract,
    }
    if record.prior_attempt_rejection is not None:
        message["prior_attempt"] = {
            "failed_attempt_count": record.attempt_number - 1,
            "last_rejection": {
                "reason_codes": list(
                    record.prior_attempt_rejection.get("reason_codes") or []
                ),
                "contract_part": record.prior_attempt_rejection.get("contract_part"),
            },
        }
    # P1-11: the report output template is derived from the public accept rule,
    # so the child knows the exact artifact shape without any hidden constraint.
    report_contract = record.public_result_contract or {}
    report_config = dict(report_contract.get("report_file") or {})
    if report_contract.get("kind") == "report_file" and report_config:
        message["report_artifact_template"] = {
            "path": report_config.get("path"),
            "must_exist": bool(report_config.get("must_exist", True)),
            "must_be_valid_json": bool(report_config.get("must_be_valid_json", True)),
            "fields_equal_evidence": list(report_config.get("fields_equal_evidence") or []),
        }
    return message


class ChildAgent:
    def __init__(
        self, backend: ModelBackend, workspace: WorkspaceRuntime,
        config: ScaffoldConfig, emitter: ProtocolEmitter,
        token_usage: TokenUsageLedger,
    ) -> None:
        self.backend = backend
        self.workspace = workspace
        self.config = config
        self.emitter = emitter
        self.token_usage = token_usage

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
            function_tool("validate_result", "Dry-run the participant-visible accept rule (report path, JSON structure, field equality) against the *current* evidence/files in this child container, WITHOUT sealing a submission. Run it before submit_result once your report artifact and evidence are ready; the reason_codes/contract_part tell you exactly what to repair. It does not substitute for doing the work.", {
                "summary": {"type": "string"},
                "evidence": {"type": "object", "description": "The exact evidence object you would pass to submit_result."},
                "files": {"type": "array", "items": {"type": "string"}, "description": "The exact files list you would pass to submit_result."},
            }, ["summary", "evidence", "files"]),
        ]

    @staticmethod
    def initial_messages(record: ChildRecord) -> list[dict[str, Any]]:
        """Build the exact system + user payload of a child's first model step."""
        return [
            {"role": "system", "content": CHILD_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(
                build_child_user_message(record),
                ensure_ascii=False, sort_keys=True,
            )},
        ]

    async def _validate_candidate(
        self, record: ChildRecord, payload: dict[str, Any],
    ) -> ResultContractValidation:
        validation = await validate_public_submission(
            child_record_contract(record),
            {
                "type": "child_completed",
                "child_id": record.child_id,
                "payload": payload,
            },
            self.workspace,
        )
        if "invalid_public_result_contract" in validation.reason_codes:
            raise ChildPublicContractDefinitionError("; ".join(validation.details))
        return validation

    async def run(
        self, record: ChildRecord, model: str, seed: int,
    ) -> ChildRunOutcome:
        messages: list[dict[str, Any]] = self.initial_messages(record)
        total_tokens = 0
        for turn_index in range(1, self.config.max_child_steps + 1):
            role = f"child:{record.child_id}"
            if not await self.token_usage.can_start():
                return ChildRunOutcome(
                    kind="resource_safety_abort",
                    payload=None,
                    hint=None,
                    tokens=total_tokens,
                    reason="episode emergency token safety cap already reached",
                )
            tools = self.tools()
            messages = compress_child_messages(
                messages,
                tools,
                budget_bytes=self.config.child_context_budget_bytes,
                keep_recent_blocks=self.config.child_keep_recent_turns,
                excerpt_chars=self.config.child_old_tool_excerpt_chars,
            )
            self.emitter.emit(
                "agent_progress", phase="model_call_started", role=role,
                turn=turn_index, model=model,
            )
            turn = await self.backend.complete(
                role=role, model=model, messages=messages,
                tools=tools, seed=_role_seed(seed, record.child_id),
            )
            usage = await self.token_usage.record(role, turn.total_tokens)
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
            if usage.crossed_now:
                self.emitter.emit(
                    "resource_safety_abort",
                    emergency_cap=self.config.emergency_total_token_cap,
                    observed_total=usage.total,
                    trigger_role=role,
                )
            if usage.tripped:
                return ChildRunOutcome(
                    kind="resource_safety_abort",
                    payload=None,
                    hint=None,
                    tokens=total_tokens,
                    reason="episode emergency token safety cap reached",
                )
            messages.append(turn.assistant_message)
            if not turn.tool_calls:
                content = (
                    turn.assistant_message.get("content")
                    or "child ended without a structured result"
                )
                return ChildRunOutcome(
                    kind="no_submission",
                    payload=None,
                    hint=None,
                    tokens=total_tokens,
                    reason=str(content),
                )
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
                    files = list(call.arguments.get("files") or [])
                    payload = {
                        "summary": str(call.arguments.get("summary", "")),
                        "evidence": evidence,
                        "files": files,
                    }
                    if call.arguments.get("patch"):
                        payload["patch"] = str(call.arguments["patch"])
                    validation = await self._validate_candidate(record, payload)
                    if not validation.valid:
                        messages.append(_tool_result(call.id, {
                            "sealed": False,
                            "error": "result does not satisfy the participant-visible contract",
                            "reason_codes": list(validation.reason_codes),
                            "details": list(validation.details),
                            "contract_part": contract_part_for_codes(
                                list(validation.reason_codes)
                            ),
                        }))
                        continue
                    hint = str(call.arguments.get("result_kind_hint", ""))
                    messages.append(_tool_result(call.id, {"sealed": True}))
                    submitted = payload, hint
                elif call.name == "validate_result":
                    evidence = call.arguments.get("evidence") or {}
                    files = list(call.arguments.get("files") or [])
                    payload = {
                        "summary": str(call.arguments.get("summary", "")),
                        "evidence": evidence,
                        "files": files,
                    }
                    validation = await self._validate_candidate(record, payload)
                    if not validation.valid:
                        messages.append(_tool_result(call.id, {
                            "valid": False,
                            "reason_codes": list(validation.reason_codes),
                            "details": list(validation.details),
                            "contract_part": contract_part_for_codes(
                                list(validation.reason_codes)
                            ),
                            "validator_output": _trim(
                                validation.validator_output, 1500,
                            ),
                        }))
                        continue
                    messages.append(_tool_result(call.id, {
                        "valid": True,
                        "note": (
                            "submit_result with these evidence/files would satisfy "
                            "the public accept rule"
                            if (record.public_result_contract or {}).get("kind")
                            == "report_file"
                            else "checked the declarative payload contract only "
                            "(no report-file accept rule is declared)"
                        ),
                    }))
                else:
                    messages.append(_tool_result(call.id, {"error": f"unknown child tool {call.name}"}))
            if submitted is not None:
                return ChildRunOutcome(
                    kind="submitted",
                    payload=submitted[0],
                    hint=submitted[1],
                    tokens=total_tokens,
                )
        return ChildRunOutcome(
            kind="step_limit_reached",
            payload=None,
            hint=None,
            tokens=total_tokens,
            reason="child reached its model-step limit without submit_result",
        )


class SubagentManager:
    def __init__(
        self,
        *,
        start: dict[str, Any],
        child_backend: ModelBackend,
        workspace: WorkspaceRuntime,
        emitter: ProtocolEmitter,
        config: ScaffoldConfig,
        token_usage: TokenUsageLedger,
        backend: ModelBackend | None = None,
    ) -> None:
        self.start = start
        # Every child turn routes through the fixed child pool backend (spec §8).
        # ``backend`` is retained as a backward-compatible alias for callers that
        # pass a single backend (e.g. the conformance mock); it is treated as the
        # child backend when no explicit ``child_backend`` is supplied.
        resolved_child = child_backend if child_backend is not None else backend
        if resolved_child is None:
            raise ValueError("SubagentManager requires a child_backend (or backend)")
        self.backend = resolved_child
        self.child_backend = resolved_child
        self.workspace = workspace
        self.emitter = emitter
        self.config = config
        self.token_usage = token_usage
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
        # P0-8/P0-9 (Task 7): per-workstream delegation history — the last
        # rejection feedback (codes + attempt + contract part), attempt counts,
        # the hard recovery-spawn counter (Step 4 cap), and the evidence digests
        # kept only as a descriptive duplicate-evidence metric (no longer gates).
        self.attempt_counts: Counter[str] = Counter()
        self.workstream_rejections: dict[str, dict[str, Any]] = {}
        self.workstream_evidence_digests: dict[str, list[str]] = defaultdict(list)
        self.recovery_spawn_counts: Counter[str] = Counter()
        self.duplicate_evidence_retries: Counter[str] = Counter()

    def unresolved_count(self) -> int:
        return sum(
            not is_runtime_terminal(record.status)
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
        return is_runtime_terminal(record.status)

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
        # P0-9: a replacement is admitted only when the previous attempt's
        # failure was reported back with an actionable public code.  A workstream
        # with no recorded rejection at all (its child cancelled, or it died
        # without a public verdict) is equally non-actionable — the initial wave
        # already covered every workstream, so any later spawn is a recovery and
        # recovery requires a real public rejection to justify it.
        feedback = self.workstream_rejections.get(workstream_id)
        if feedback is None or not feedback.get("actionable"):
            result = {
                "error": (
                    f"last rejection of {workstream_id!r} carried no actionable "
                    f"public code ({(feedback or {}).get('reason_codes') or []}); "
                    "re-delegation refused until the submission contract is repaired"
                ),
                "budget_consumed": False,
            }
            self.emitter.emit(
                "delegation_validation_error", requested_workstream=workstream_id,
                reason=result["error"], budget_consumed=False,
            )
            return result
        # Task 7 (Step 4): a hard per-workstream recovery cap replaces the
        # digest-based no-information bound.  An admitted replacement consumes
        # one recovery slot regardless of whether its free-text evidence digest
        # changed, so the same workstream can be retried at most
        # ``max_recovery_spawns_per_workstream`` times.
        if self.recovery_spawn_counts[workstream_id] >= self.config.max_recovery_spawns_per_workstream:
            result = {
                "error": (
                    f"maximum recovery attempts for workstream "
                    f"{workstream_id!r} reached"
                ),
                "budget_consumed": False,
            }
            self.emitter.emit(
                "delegation_validation_error", requested_workstream=workstream_id,
                reason=result["error"], budget_consumed=False,
            )
            return result
        # Build the prospective record before consuming a recovery slot so an
        # impossible public/context contract is rejected without changing the
        # model's bounded spawn allowance.
        attempt_number = self.attempt_counts[workstream_id] + 1
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
            attempt_number=attempt_number,
            prior_attempt_rejection=self.workstream_rejections.get(workstream_id),
        )
        try:
            compress_child_messages(
                ChildAgent.initial_messages(record),
                ChildAgent.tools(),
                budget_bytes=self.config.child_context_budget_bytes,
                keep_recent_blocks=self.config.child_keep_recent_turns,
                excerpt_chars=self.config.child_old_tool_excerpt_chars,
            )
        except ChildContextBudgetError as exc:
            result = {
                "error": (
                    f"recovery child first call exceeds the child context budget "
                    f"({exc}); re-delegation refused"
                ),
                "budget_consumed": False,
            }
            self.emitter.emit(
                "delegation_validation_error", requested_workstream=workstream_id,
                reason=result["error"], budget_consumed=False,
            )
            return result
        self.attempt_counts[workstream_id] += 1
        self.recovery_spawn_counts[workstream_id] += 1
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
            self.attempt_counts[workstream_id] += 1
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
                self.token_usage,
            )
            outcome = await asyncio.wait_for(
                agent.run(
                    record, self.config.child_model, int(self.start["agent_seed"]),
                ),
                timeout=self.config.child_timeout_sec,
            )
            record.tokens = outcome.tokens
            if outcome.kind != "submitted":
                record.status = outcome.kind
                record.decision = outcome.kind
                event_type = {
                    "step_limit_reached": "child_step_limit_reached",
                    "resource_safety_abort": "child_resource_safety_abort",
                    "no_submission": "child_no_submission",
                }[outcome.kind]
                fields: dict[str, Any] = {
                    "child_id": record.child_id,
                    "reason": outcome.reason or outcome.kind,
                }
                self.emitter.emit(event_type, **fields)
                self._delivery_event.set()
                return
            assert outcome.payload is not None
            self._completion_counter += 1
            completion_id = f"completion-{self._completion_counter}"
            record.status = "completed_hidden"
            record.completion_id = completion_id
            record.payload = outcome.payload
            # P0-9: track evidence increment across attempts.  A sealed submission
            # whose evidence bytes repeat an earlier attempt's contributes no new
            # information, and re-delegation on it is bounded to one retry.
            workstream_id = record.work_units[0] if record.work_units else None
            if workstream_id:
                self._record_workstream_evidence(
                    workstream_id, outcome.payload, record.child_id,
                )
            self.completion_to_child[completion_id] = record.child_id
            self.emitter.emit(
                "child_completed",
                child_id=record.child_id,
                completion_id=completion_id,
                payload=outcome.payload,
                usage={"tokens": outcome.tokens},
            )
        except ChildPublicContractDefinitionError as exc:
            record.status = "infrastructure_failed"
            record.decision = "infrastructure_failed"
            self.emitter.emit(
                "infrastructure_failure",
                component="case_contract",
                child_id=record.child_id,
                detail=str(exc),
            )
            self._delivery_event.set()
        except ChildContextBudgetError as exc:
            record.status = "infrastructure_failed"
            record.decision = "infrastructure_failed"
            self.emitter.emit(
                "infrastructure_failure",
                component="child_context_budget",
                child_id=record.child_id,
                detail=str(exc),
            )
            self._delivery_event.set()
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
            # A gateway-owned designed child terminal (timeout/crash) carries a
            # synthetic completion_id the adapter never saw as a real child
            # completion.  Bind it to the delivered child_id when it is a known
            # in-flight child, so the designed failure reaches main instead of
            # being dropped as "unknown completion" (spec §6.2).
            fallback_child_id = str(delivery.get("child_id", ""))
            if delivery.get("terminal_outcome") and fallback_child_id in self.children:
                child_id = fallback_child_id
            else:
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
        workstream_id = record.work_units[0] if record.work_units else None
        # P0-8: every rejection event carries the failed-workstream attempt count
        # and the contract part to repair, and the runtime remembers the last
        # public feedback so a replacement delegation carries it (P0-9 gating).
        reason_codes = [str(item) for item in rejection.get("reason_codes") or []]
        public_codes = [code for code in reason_codes if code in PUBLIC_RESULT_REJECTION_CODES]
        feedback = {
            "reason_codes": public_codes,
            "actionable": bool(public_codes),
            "contract_part": contract_part_for_codes(public_codes),
            "attempt_count": self.attempt_counts.get(workstream_id or "", 0),
        }
        if workstream_id:
            self.workstream_rejections[workstream_id] = feedback
        record.contract_rejection = dict(rejection)
        record.contract_rejection["attempt_count"] = feedback["attempt_count"]
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

    def _record_workstream_evidence(
        self, workstream_id: str, payload: Any, child_id: str,
    ) -> None:
        """Record the sealed payload's evidence digest against prior attempts.

        Task 7: the digest comparison is a *descriptive* metric only — it no
        longer bounds re-delegation (that is the hard per-workstream recovery cap
        in ``spawn``).  A payload whose evidence bytes repeat an earlier
        attempt's is reported as a duplicate-evidence retry.
        """
        digest = canonical_digest((payload or {}).get("evidence") or {})
        if digest in self.workstream_evidence_digests[workstream_id]:
            self.duplicate_evidence_retries[workstream_id] += 1
            self.emitter.emit(
                "duplicate_evidence_retry_detected",
                child_id=child_id,
                workstream_id=workstream_id,
                evidence_digest=digest,
                duplicate_evidence_retries=self.duplicate_evidence_retries[workstream_id],
            )
        else:
            self.workstream_evidence_digests[workstream_id].append(digest)

    def statuses(self) -> list[dict[str, Any]]:
        # Lifecycle + workstream identity only. Held completion payloads stay
        # hidden until the main model explicitly waits for and acknowledges them.
        # Rejections are projected through ``public_rejection`` so every surface
        # (async statuses, linear bundle) carries the same public reason codes,
        # the contract part to repair, and the failed-attempt count.
        rows: list[dict[str, Any]] = []
        for record in self.children.values():
            workstream_id = record.work_units[0] if record.work_units else None
            rejection = None
            if record.contract_rejection is not None:
                rejection = public_rejection(
                    record.contract_rejection, workstream_id=workstream_id,
                )
            rows.append({
                "child_id": record.child_id,
                "workstream_id": workstream_id,
                "status": record.status,
                "targets": record.targets,
                "task": record.task[:400],
                "decision": record.decision,
                "contract_rejection_reason_codes": (
                    list(rejection.get("reason_codes") or []) if rejection else []
                ),
                "contract_part": rejection.get("contract_part") if rejection else None,
                "attempt_count": rejection.get("attempt_count") if rejection else None,
            })
        return rows

    async def wait(self, child_ids: list[str], timeout: float, return_when: str) -> dict[str, Any]:
        selected = child_ids or list(self.children)

        def ready() -> bool:
            states = [self.children[item].status for item in selected if item in self.children]
            if not states:
                return False
            return (
                all(is_runtime_terminal(state) for state in states)
                if return_when == "all"
                else any(is_runtime_terminal(state) for state in states)
            )

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
        if is_runtime_terminal(record.status) or record.status not in {
            "queued", "spawned", "starting", "running",
        }:
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
        main_backend: ModelBackend | None = None,
        child_backend: ModelBackend | None = None,
        backend: ModelBackend | None = None,
        workspace: WorkspaceRuntime,
        emitter: ProtocolEmitter,
        delivery_reader: DeliveryReader,
    ) -> None:
        self.start = start
        self.config = config
        # Dual provider roles (spec §8): the main agent routes through
        # ``main_backend`` and every child routes through ``child_backend``.
        # ``backend`` is retained as a backward-compatible alias for callers
        # that pass a single backend (e.g. the conformance mock); it is treated
        # as the main backend and, when no child backend is supplied, the child
        # backend too.
        resolved_main = main_backend if main_backend is not None else backend
        if resolved_main is None:
            raise ValueError("ReferenceScaffold requires a main_backend (or backend)")
        self.main_backend = resolved_main
        self.child_backend = child_backend if child_backend is not None else resolved_main
        self.backend = self.main_backend
        self.workspace = workspace
        self.emitter = emitter
        self.delivery_reader = delivery_reader
        # Tokens are descriptive diagnostics in v10.1. The only runtime guard
        # is a deliberately high, shared emergency fuse for provider runaway.
        self.token_usage = TokenUsageLedger(
            emergency_cap=config.emergency_total_token_cap,
        )
        self.manager = SubagentManager(
            start=start, child_backend=self.child_backend, workspace=workspace,
            emitter=emitter, config=config, token_usage=self.token_usage,
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
            function_tool("finish", "End the episode immediately with the model's declared status and summary. Commit, verification, pending-delivery, and response-window state are recorded as diagnostics; the independent benchmark verifier decides actual task success.", {
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
            "final artifacts, and verify when useful. Calling finish always ends the episode immediately; the "
            "benchmark records closure state and independently scores the produced workspace.\n\n"
            f"Public protocol catalog: {json.dumps(public_catalog, sort_keys=True)}\n\n"
            f"Evaluation guidance: {self.start.get('guidance', '')}"
        )

    async def _maybe_present_linear_bundle(self) -> bool:
        """Linear: show one atomic terminal bundle to the main model (spec §6).

        Waits until the whole benchmark wave resolves, builds one stable bundle
        sorted by workstream_id, injects it as a single ASYNC_RBENCH_LINEAR_BUNDLE
        message, and emits the ready/presented boundaries. Returns False when the
        wave did not reach a terminal state in time: an infrastructure
        failure, recorded so the episode is unscored rather than presented to
        the model (or silently marked scored with ``main_tokens=0``).

        The wait bound is the benchmark-owned child lifecycle cap
        (start barrier + ``child_timeout_sec``), not the much shorter
        per-terminal-command timeout.  A child may legitimately keep running its
        model turns up to ``child_timeout_sec`` after the wave barrier; cutting
        the bundle wait at the terminal-command cap fires while a healthy wave
        is still in its allowed lifecycle and produces a scored-but-empty Linear
        episode.
        """
        wait_cap = self.config.start_barrier_timeout_sec + self.config.child_timeout_sec
        if not await self.manager.wait_linear_bundle(timeout=wait_cap):
            self.emitter.emit(
                "infrastructure_failure", component="linear_bundle_barrier",
                detail=(
                    "initial wave did not reach a terminal bundle within the child "
                    f"lifecycle cap ({wait_cap}s = start_barrier "
                    f"{self.config.start_barrier_timeout_sec}s + child_timeout "
                    f"{self.config.child_timeout_sec}s)"
                ),
            )
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

    def _emit_runtime_metadata_snapshot(self) -> None:
        """Persist provider-resolved identity for both roles before a timeout.

        Merges the main- and child-backend observations into one
        ``participant_runtime_metadata`` event so the runner sees the resolved
        model and child-pool identity for every role (spec §8).  No event is
        emitted when neither backend has yet observed a model response.
        """
        observations: list[dict[str, Any]] = []
        roles: dict[str, dict[str, Any]] = {}
        for backend in (self.main_backend, self.child_backend):
            metadata = getattr(backend, "runtime_metadata", lambda: {"model_observations": []})()
            metadata = metadata or {}
            for obs in metadata.get("model_observations") or []:
                observations.append(obs)
            role = metadata.get("role")
            if role:
                roles[str(role)] = {
                    key: value for key, value in metadata.items()
                    if key not in {"model_observations"}
                }
        if not observations and not roles:
            return
        payload: dict[str, Any] = {"model_observations": observations}
        if roles:
            payload["roles"] = roles
        if self.config.child_pool_id:
            payload["child_pool_id"] = self.config.child_pool_id
        self.emitter.emit("participant_runtime_metadata", **payload)

    async def run_one_main_and_one_child_turn(self) -> None:
        """Test driver: route one main turn and one child turn through their roles.

        Exercises the dual-backend wiring directly: the main call uses
        ``main_backend``, the child turn uses ``child_backend`` (spec §8).  The
        child record is a benchmark-owned initial-wave workstream so the child's
        single ``submit_result`` seals it on the first model turn.
        """
        if not self.messages:
            self.messages = [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": str(self.start["instruction"])},
            ]
        main_turn = await self.main_backend.complete(
            role="main",
            model=self.config.main_model,
            messages=self.messages,
            tools=self.main_tools(),
            seed=_role_seed(int(self.start["agent_seed"]), "main"),
        )
        self.messages.append(main_turn.assistant_message)
        record = ChildRecord(
            child_id="child-1",
            task="delegated workstream",
            work_units=["wal_recovery"],
            targets=[],
            expected_output="out",
            priority="normal",
            initial_wave=True,
            # Task 4 fail-closed contract: carry the workstream's public result
            # contract so the child submission is validated against a real `kind`.
            public_result_contract=dict(
                (self.start.get("workstream_contracts") or {}).get(
                    "wal_recovery", {}
                ).get("public_result_contract", {})
            ),
        )
        agent = ChildAgent(
            self.child_backend, self.workspace, self.config, self.emitter,
            self.token_usage,
        )
        await agent.run(record, self.config.child_model, int(self.start["agent_seed"]))

    def _emit_token_usage_snapshot(self) -> None:
        """Persist final descriptive token usage on every termination path."""
        self.emitter.emit("token_usage_snapshot", **self.token_usage.snapshot)

    async def run(self) -> None:
        try:
            await self._run()
        finally:
            self._emit_token_usage_snapshot()

    async def _run(self) -> None:
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
        for step_index in range(self.next_turn_index, self.config.max_main_steps + 1):
            self.next_turn_index = step_index
            if not await self.token_usage.can_start():
                self.finish_status = "resource_safety_abort"
                self.final_summary = "emergency total-token safety fuse was already tripped"
                return
            try:
                # Select at most one FIFO occurrence while no response window is
                # open. Preparation remains evaluator-owned, but it is no longer
                # a gate on whether the model may end the episode.
                candidate = self.manager.select_presentable()
                prepared_occurrence_id: str | None = None
                if candidate is not None:
                    prepared_occurrence_id = await self._prepare_presentation(
                        candidate, f"t{step_index}",
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
                    turn=step_index, model=self.config.main_model,
                )
                turn = await self.main_backend.complete(
                    role="main",
                    model=self.config.main_model,
                    messages=messages,
                    tools=self.main_tools(),
                    seed=_role_seed(int(self.start["agent_seed"]), "main"),
                )
                if prepared_occurrence_id is not None:
                    self.manager.mark_presented(
                        prepared_occurrence_id,
                        turn_id=f"t{step_index}",
                        window_id=f"w{step_index}",
                    )
                usage = await self.token_usage.record("main", turn.total_tokens)
                self.emitter.emit(
                    "agent_progress", phase="model_call_finished", role="main",
                    turn=step_index, tokens=turn.total_tokens,
                )
                self._emit_runtime_metadata_snapshot()
                if usage.crossed_now:
                    self.emitter.emit(
                        "resource_safety_abort",
                        emergency_cap=self.config.emergency_total_token_cap,
                        observed_total=usage.total,
                        trigger_role="main",
                    )
                if usage.tripped:
                    self.finish_status = "resource_safety_abort"
                    self.final_summary = "emergency total-token safety fuse tripped"
                    return
            except Exception as exc:
                LOGGER.exception("main model call failed")
                self.emitter.emit(
                    "infrastructure_failure",
                    component="model_request", detail=f"main model call failed: {exc}",
                )
                self.finish_status = "incomplete"
                self.final_summary = f"main model failure: {exc}"
                return
            messages.append(turn.assistant_message)
            self.manager.presentation_queue.record_turn()
            self._close_presentation_window()
            if (
                not self.manager.presentation_queue.has_pending()
                and self.manager.presentation_queue.active_window is None
            ):
                self.manager._delivery_event.clear()
            if not turn.tool_calls:
                self.finish_status = "incomplete"
                self.final_summary = str(
                    turn.assistant_message.get("content") or "main ended without finish"
                )
                self.emitter.emit(
                    "main_implicit_stop", summary=self.final_summary,
                )
                return
            self._current_turn_id = f"t{step_index}"
            executed_tool_count = 0
            for call in turn.tool_calls:
                result = await self._execute_main_tool(call)
                messages.append(_tool_result(call.id, result))
                executed_tool_count += 1
                if self.finished:
                    break
            self.emitter.emit(
                "main_turn_completed",
                turn_id=f"t{step_index}",
                tool_count=executed_tool_count,
            )
            await asyncio.sleep(0)
            self.next_turn_index = step_index + 1
            if self.finished:
                return
        self.finish_status = "step_limit_reached"
        self.final_summary = "main model-step limit reached"
        self.emitter.emit(
            "step_limit_reached", role="main", limit=self.config.max_main_steps,
        )

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
            pending_occurrence_count = len(
                self.manager.presentation_queue.pending_occurrence_ids
            )
            open_window = (
                self.manager.presentation_queue.active_window is not None
                and self.manager.presentation_queue.active_window.active
            )
            final_commit_current = (
                self._final_commit_revision == self._accepted_state_revision
            )
            verification_current = (
                self._verification_revision == self._accepted_state_revision
                and self._verification_passed
            )
            closure_complete = (
                pending_occurrence_count == 0
                and not open_window
                and final_commit_current
                and verification_current
            )
            self.emitter.emit(
                "finish_invoked",
                requested_status=requested_status,
                pending_occurrence_count=pending_occurrence_count,
                active_response_window=open_window,
                final_commit_current=final_commit_current,
                verification_current=verification_current,
                closure_complete=closure_complete,
            )
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
