"""P1-16: Linear/Async pairing invariance guard.

The pairing design promises that the two execution paths can only differ in
when/how results are presented to the main model (async: per-result
occurrences; linear: one atomic bundle after the wave resolves).  Everything
the child technically experiences --- its prompt, the public contract it is
graded against, the private validator rendered from that contract, the token
budget accounting, and the terminal classification of its outcome --- must be
identical across both arms.  Any drift invalidates the Linear/Async
head-to-head, so it is guarded here as an automated invariant suite, not as a
manual verification.

Each test pins one facet of the invariant over the paper cases, including the
two mab target cases used for the final re-run.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from async_rbench.evaluation.budget import build_budget_ledger
from async_rbench.evaluation.model_backend import ModelTurn, ToolCall
from async_rbench.evaluation.report_contract import report_contract_errors
from async_rbench.evaluation.runner import EpisodeConfig, _make_start
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import (
    CHILD_SYSTEM_PROMPT, ChildAgent, ChildRecord, ReferenceScaffold,
    build_child_user_message,
)
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]

# The paper case sample plus the two mab re-run target cases.
INVARIANT_CASES = (
    "data-recovery-service",
    "mab-dependency-unblock-09f3ab60d7",
    "mab-late-test-evidence-7d09ace3d3",
)


def _start(case_id: str, mode: str) -> dict:
    case_path = ROOT / "cases" / case_id / "public_case.yaml"
    case = load_case(case_path).raw
    import yaml

    task = yaml.safe_load((case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8"))
    config = EpisodeConfig(
        episode_id="test-episode", case_id=case_id, execution_mode=mode,
        guidance="incentive", agent_seed=1, adapter_command=[sys.executable],
        output_dir=ROOT / "artifacts" / "test-unused", use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _scaffold(start: dict) -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(
        None, {"backend": "scripted_test", "workspace_mode": "disabled"},
    )
    return ReferenceScaffold(
        start=start,
        config=config,
        backend=ScriptedTestBackend(),
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(),
    )


def _records_from_initial_wave(scaffold: ReferenceScaffold) -> list[ChildRecord]:
    manager = scaffold.manager
    manager._launch_queued = lambda: None  # do not actually run the children
    manager.spawn_initial_wave()
    return list(manager.children.values())


# --- Facet 1: the public start / contracts are mode-independent ---------------


@pytest.mark.parametrize("case_id", INVARIANT_CASES)
def test_public_start_is_identical_across_modes(case_id: str) -> None:
    linear = _start(case_id, "linear")
    async_ = _start(case_id, "async")
    assert linear["execution_mode"] == "linear"
    assert async_["execution_mode"] == "async"
    left = {key: value for key, value in linear.items() if key != "execution_mode"}
    right = {key: value for key, value in async_.items() if key != "execution_mode"}
    # Only the execution_mode key may differ: the instruction, the public
    # workstream contracts (incl. public_result_contract), the initial wave,
    # the allowed-work-unit set, artifacts and public checks must be identical.
    assert left == right


@pytest.mark.parametrize("case_id", INVARIANT_CASES)
def test_private_validator_is_rendered_from_the_public_contract(case_id: str) -> None:
    """P0-4 as a mode-invariance base: the validator is a deterministic render
    of the public rule (``report_contract_errors`` enforces the exact render,
    report_path == required_files[0], fields ⊆ required evidence, allowed-file
    membership).  Since ``load_case`` output is shared by both modes, no
    mode-dependent validator can exist.
    """
    case_path = ROOT / "cases" / case_id / "public_case.yaml"
    case = load_case(case_path).raw
    for workstream in case["delegation_workstreams"]:
        errors = report_contract_errors(workstream)
        assert errors == [], f"{workstream['id']}: {errors}"


# --- Facet 2: the child record / prompt / tools are mode-independent ----------


@pytest.mark.parametrize("case_id", INVARIANT_CASES)
def test_initial_wave_records_are_identical_across_modes(case_id: str) -> None:
    linear = _records_from_initial_wave(_scaffold(_start(case_id, "linear")))
    async_ = _records_from_initial_wave(_scaffold(_start(case_id, "async")))
    assert len(linear) == len(async_) > 0
    for left, right in zip(linear, async_):
        # Every record field (task, work_units, targets, expected_output,
        # priority, attempt_number, required evidence/files list, the public
        # result contract, evidence schema, initial_wave flag) must match.
        for field_name in ChildRecord.__dataclass_fields__:
            assert getattr(left, field_name) == getattr(right, field_name), (
                f"{field_name} differs between Linear/Async records "
                f"({getattr(left, field_name)!r} vs {getattr(right, field_name)!r})"
            )


@pytest.mark.parametrize("case_id", INVARIANT_CASES)
def test_child_user_message_is_identical_across_modes(case_id: str) -> None:
    linear = _records_from_initial_wave(_scaffold(_start(case_id, "linear")))
    async_ = _records_from_initial_wave(_scaffold(_start(case_id, "async")))
    for left, right in zip(linear, async_):
        assert build_child_user_message(left) == build_child_user_message(right)
    # First attempts must not carry a phantom prior_attempt block: the key is
    # added to the participant-visible user message ONLY when real rejection
    # feedback exists, so inspect the built message, never the raw task text.
    assert "prior_attempt" not in build_child_user_message(linear[0])


def test_child_system_prompt_is_a_single_mode_free_constant() -> None:
    # The prompt is one constant shared by both arms; it must not speak either
    # arm's execution vocabulary (identical child ⇒ no arm-favouring capability
    # change), while keeping the public /app-exploration preference and the
    # self-check tool guidance.
    prompt = CHILD_SYSTEM_PROMPT.lower()
    for token in (
        "linear",
        "async",
        "bundle",
        "leaderboard",
        "occurrence",
        # Evaluator-private concepts must never surface in a participant-visible
        # prompt: a hidden validator or a private rule set.
        "hidden validator",
        "private",
    ):
        assert token not in prompt
    assert "prefer" in prompt
    assert "validate_result" in prompt
    tools = {item["function"]["name"] for item in ChildAgent.tools()}
    assert tools == {"terminal", "submit_result", "validate_result"}


# --- Facet 3: single mode-free validation site --------------------------------


def test_gateway_validation_has_exactly_one_mode_free_call_site() -> None:
    runner_src = (ROOT / "async_rbench" / "evaluation" / "runner.py").read_text(
        encoding="utf-8"
    )
    assert runner_src.count("validate_completion_contract(") == 1
    contract_src = (ROOT / "async_rbench" / "evaluation" / "result_contract.py").read_text(
        encoding="utf-8"
    )
    assert contract_src.count("def validate_completion_contract") == 1


# --- Facet 4: budget layout --------------------------------------------------


def test_budget_layout_is_identical_for_both_arms() -> None:
    config = ScaffoldConfig.from_file(
        None, {"backend": "scripted_test", "workspace_mode": "disabled"},
    )
    linear = build_budget_ledger(
        "linear",
        child_shared=config.budget_child_shared,
        main_pre=config.budget_main_pre,
        main_post=config.budget_main_post,
        main_total=config.budget_main_total,
    )
    async_ = build_budget_ledger(
        "async",
        child_shared=config.budget_child_shared,
        main_pre=config.budget_main_pre,
        main_post=config.budget_main_post,
        main_total=config.budget_main_total,
    )
    # The child budget is one identical shared pool in both modes: the model's
    # child-side resource ceiling must not change across arms.
    assert linear.pool("child_shared").maximum == async_.pool("child_shared").maximum
    # The main side is only SPLIT differently (pre/post vs one merged pool);
    # the total main budget is identical.
    assert (
        linear.pool("main_total").maximum
        == async_.pool("main_pre").maximum + async_.pool("main_post").maximum
    )
    assert config.budget_main_total == config.budget_main_pre + config.budget_main_post


# --- Facet 5: terminal classification is identical ----------------------------
#
# Each of the six terminal kinds is produced by going through the manager's OWN
# handlers: ``_run_child`` runs a real (mock-backend) child agent to its
# outcome, and a sealed/designed result is then routed through
# ``handle_delivery`` / ``handle_rejection``.  The test never mutates
# ``record.status`` / ``record.decision`` by hand.  Every scenario is run once
# on a Linear scaffold and once on an Async scaffold (each trimmed to the same
# single workstream), and the terminal classification, reason codes, attempt
# number, tokens and public contract verdict must be IDENTICAL; only the result
# presentation/arrival events may differ.


class NoToolBackend:
    """A child that never calls a tool.  With budget it ends ``no_submission``;
    with an empty shared pool it ends ``token_budget_exhausted``."""

    async def complete(self, **_: Any) -> ModelTurn:
        return ModelTurn(
            assistant_message={"role": "assistant", "content": "not submitted"},
            tool_calls=[],
            total_tokens=7,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}


class NonSubmitToolBackend:
    """A child that only calls the terminal tool (never submit_result): bounded
    by ``max_child_turns`` the manager records ``turn_limit_exhausted``."""

    def __init__(self) -> None:
        self.turn = 0

    async def complete(self, **_: Any) -> ModelTurn:
        self.turn += 1
        call_id = f"terminal-{self.turn}"
        arguments = {"command": "echo still-working"}
        return ModelTurn(
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps(arguments),
                    },
                }],
            },
            tool_calls=[ToolCall(call_id, "terminal", arguments)],
            total_tokens=11,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}


def _normalize_row(row: dict) -> tuple:
    return (
        row["status"],
        tuple(row.get("contract_rejection_reason_codes") or ()),
        row.get("contract_part"),
        row.get("attempt_count"),
    )


def _normalize_entry(entry: dict) -> tuple:
    rejection = entry.get("rejection") or {}
    return (
        entry["status"],
        tuple(rejection.get("reason_codes") or ()),
        rejection.get("contract_part"),
        rejection.get("attempt_count"),
    )


def _single_worker_start(mode: str) -> dict:
    """A data-recovery-service start trimmed to its single ``wal_recovery``
    worker, so a fresh pair of scaffolds can be built for every scenario."""
    start = _start("data-recovery-service", mode)
    workstream_id = "wal_recovery"
    wave_ids = [str(item.get("workstream_id")) for item in start["initial_wave"]]
    assert workstream_id in wave_ids
    start["initial_wave"] = [
        item for item in start["initial_wave"]
        if str(item.get("workstream_id")) == workstream_id
    ]
    start["allowed_work_units"] = [workstream_id]
    start["workstream_contracts"] = {
        workstream_id: start["workstream_contracts"][workstream_id]
    }
    return start


def _terminal_scaffold(
    mode: str, backend: Any, *, max_child_turns: int = 40,
) -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "workspace_mode": "disabled",
        "max_child_turns": max_child_turns,
    })
    return ReferenceScaffold(
        start=_single_worker_start(mode),
        config=config,
        backend=backend,
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
    )


#: The presentation/arrival boundaries that ARE the allowed Linear/Async delta.
_PRESENTATION_EVENT_TYPES = frozenset({
    "result_available",
    "adapter_queued",
    "result_presented",
})


def _non_presentation_types(events: list[dict]) -> list[str]:
    return [
        event["type"] for event in events
        if event["type"] not in _PRESENTATION_EVENT_TYPES
    ]


TERMINAL_SCENARIOS = (
    "public_valid_submission",
    "public_contract_rejection",
    "token_budget_exhaustion",
    "no_submission",
    "turn_limit_exhaustion",
    "designed_timeout",
)

#: The mock backend class that produces each scenario (fresh per arm).
_SCENARIO_BACKEND = {
    "public_valid_submission": ScriptedTestBackend,
    "public_contract_rejection": ScriptedTestBackend,
    "token_budget_exhaustion": NoToolBackend,
    "no_submission": NoToolBackend,
    "turn_limit_exhaustion": NonSubmitToolBackend,
    "designed_timeout": NoToolBackend,
}

#: Scenarios that bound the child's turns instead of running to the default.
_SCENARIO_MAX_CHILD_TURNS = {"turn_limit_exhaustion": 2}

#: The manager-recorded terminal each scenario must reach (Task 8 keeps these
#: runtime status strings; the deeper scorer taxonomy is guarded separately).
_SCENARIO_TERMINAL_STATUS = {
    "public_valid_submission": "delivered",
    "public_contract_rejection": "contract_rejected",
    "token_budget_exhaustion": "token_budget_exhausted",
    "no_submission": "no_submission",
    "turn_limit_exhaustion": "turn_limit_exhausted",
    "designed_timeout": "delivered",
}

#: Token spend of each scenario's real child run.
_SCENARIO_TOKENS = {
    "public_valid_submission": 10,
    "public_contract_rejection": 10,
    "token_budget_exhaustion": 0,
    "no_submission": 21,
    "turn_limit_exhaustion": 22,
    "designed_timeout": 0,
}

#: The canonical public projection tuple both surfaces must report per scenario.
_SCENARIO_PROJECTION = {
    "public_valid_submission": ("delivered", (), None, None),
    "public_contract_rejection": (
        "contract_rejected",
        ("report_file_missing", "report_json_invalid"),
        "report_file",
        1,
    ),
    "token_budget_exhaustion": ("token_budget_exhausted", (), None, None),
    "no_submission": ("no_submission", (), None, None),
    "turn_limit_exhaustion": ("turn_limit_exhausted", (), None, None),
    "designed_timeout": ("delivered", (), None, None),
}

#: Scenarios in which the async arm enqueues one presentation occurrence.
_ASYNC_PRESENTS = frozenset({"public_valid_submission", "designed_timeout"})


async def _drive_terminal(manager: Any, record: ChildRecord, scenario: str) -> None:
    """Produce one terminal outcome exclusively through the manager's handlers."""
    child_id = record.child_id
    if scenario == "public_valid_submission":
        await manager._run_child(record)
        await manager.handle_delivery({
            "completion_id": record.completion_id,
            "payload": record.payload,
            "payload_sha256": "a" * 64,
            "child_id": child_id,
        })
    elif scenario == "public_contract_rejection":
        await manager._run_child(record)
        await manager.handle_rejection({
            "completion_id": record.completion_id,
            "reason_codes": ["report_file_missing", "report_json_invalid"],
            "child_id": child_id,
        })
    elif scenario == "token_budget_exhaustion":
        # The child's shared pool has no remaining budget: admission is refused,
        # ending the attempt without a submission.
        manager.token_budget.maximum = 0
        await manager._run_child(record)
    elif scenario == "no_submission":
        await manager._run_child(record)
    elif scenario == "turn_limit_exhaustion":
        await manager._run_child(record)
    elif scenario == "designed_timeout":
        # A designed terminal is a gateway-owned delivery that names the running
        # child (its synthetic completion was never a real child completion), so
        # ``handle_delivery`` binds it through ``terminal_outcome`` + child_id.
        await manager.handle_delivery({
            "completion_id": "terminal:ev-1",
            "terminal_outcome": "timeout",
            "evaluator_terminal_reason": "designed child timeout",
            "child_id": child_id,
        })
    else:
        raise AssertionError(f"unknown terminal scenario {scenario!r}")


@pytest.mark.parametrize("scenario", TERMINAL_SCENARIOS)
def test_termination_classification_is_identical_across_modes(scenario: str) -> None:
    """Six real terminal outcomes, each driven through the scaffold's own event
    handlers once for a Linear scaffold and once for an Async scaffold.

    The terminal class (the manager-recorded status + decision), reason codes,
    attempt number, tokens and public contract verdict must be IDENTICAL across
    modes; only the presentation/arrival boundary events may differ.
    """
    async def exercise() -> None:
        backend_cls = _SCENARIO_BACKEND[scenario]
        max_turns = _SCENARIO_MAX_CHILD_TURNS.get(scenario, 40)
        linear = _terminal_scaffold("linear", backend_cls(), max_child_turns=max_turns)
        async_ = _terminal_scaffold("async", backend_cls(), max_child_turns=max_turns)
        for scaffold in (linear, async_):
            scaffold.manager._launch_queued = lambda: None  # drive children manually
            scaffold.manager.spawn_initial_wave()
            assert len(scaffold.manager.children) == 1
            record = next(iter(scaffold.manager.children.values()))
            await _drive_terminal(scaffold.manager, record, scenario)

        lin_record = next(iter(linear.manager.children.values()))
        asy_record = next(iter(async_.manager.children.values()))

        # First-attempt classification, identical across the arms.
        assert lin_record.attempt_number == asy_record.attempt_number == 1
        # Every scenario lands on the same canonical terminal class (status) and
        # the same reason decision in both arms.
        assert lin_record.status == asy_record.status == _SCENARIO_TERMINAL_STATUS[scenario]
        assert lin_record.decision == asy_record.decision
        # The tokens the child actually spent are identical across the arms.
        assert lin_record.tokens == asy_record.tokens == _SCENARIO_TOKENS[scenario]

        # The two surfaces project the SAME public contract verdict: the async
        # status row and the linear bundle entry collapse to one tuple, and both
        # arms' manager statuses() are byte-identical.
        async_row = async_.manager.statuses()[0]
        linear_entry = linear.manager.build_linear_bundle()["workstreams"][0]
        assert _normalize_row(async_row) == _normalize_entry(linear_entry)
        assert _normalize_entry(linear_entry) == _SCENARIO_PROJECTION[scenario]
        assert linear.manager.statuses() == async_.manager.statuses()

        # The designed timeout is a distinct terminal layered on top of the
        # shared "delivered" state: its gateway delivery carries terminal_outcome.
        if scenario == "designed_timeout":
            for scaffold in (linear, async_):
                record = next(iter(scaffold.manager.children.values()))
                assert record.delivery is not None
                assert record.delivery.get("terminal_outcome") == "timeout"
                assert record.payload is None

        # The whole wave resolves in both arms.
        assert linear.manager.unresolved_count() == 0
        assert async_.manager.unresolved_count() == 0
        assert linear.manager.linear_bundle_ready() is True
        assert async_.manager.linear_bundle_ready() is True

        # ONLY presentation/arrival events may differ: async enqueues an
        # occurrence exactly for delivery-bearing scenarios; linear never does.
        assert async_.manager.presentation_queue.has_pending() is (
            scenario in _ASYNC_PRESENTS
        )
        assert linear.manager.presentation_queue.has_pending() is False
        assert not any(
            event["type"] in _PRESENTATION_EVENT_TYPES
            for event in linear.emitter.events
        )
        assert _non_presentation_types(async_.emitter.events) == (
            _non_presentation_types(linear.emitter.events)
        )

        # Both surfaces stay participant-safe: no evaluator-private roles leak.
        encoded = json.dumps(linear.manager.build_linear_bundle(), sort_keys=True)
        for forbidden in ("result_kind", "validator_command", "hidden_checks"):
            assert forbidden not in encoded

    asyncio.run(exercise())


def test_initial_wave_declaration_validation_is_mode_independent() -> None:
    """A malformed wave declaration is an infrastructure failure in BOTH arms;
    no mode may receive a differently-started benchmark-owned wave."""
    async def exercise() -> None:
        linear = _scaffold(_start("data-recovery-service", "linear"))
        async_ = _scaffold(_start("data-recovery-service", "async"))
        for scaffold in (linear, async_):
            scaffold.manager._launch_queued = lambda: None
            scaffold.manager.start["initial_wave"] = []  # break one-to-one map
            result = scaffold.manager.spawn_initial_wave()
            assert "budget_consumed" in result  # error surface, not a spawn
            assert not scaffold.manager.children
            types = [event.get("type") for event in scaffold.emitter.events]
            assert "infrastructure_failure" in types

    asyncio.run(exercise())
