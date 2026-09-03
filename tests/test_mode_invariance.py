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

import pytest

from async_rbench.evaluation.budget import build_budget_ledger
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


def _child_id_for(manager, workstream_id: str) -> str:
    for child_id, record in manager.children.items():
        if record.work_units and record.work_units[0] == workstream_id:
            return child_id
    raise AssertionError(f"no spawned record for workstream {workstream_id}")


def _bind_completion(manager, child_id: str) -> str:
    completion_id = f"comp-{child_id}"
    manager.completion_to_child[completion_id] = child_id
    return completion_id


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
    # First attempts must not carry a phantom prior_attempt block.
    assert "prior_attempt" not in json.dumps(linear[0].task, sort_keys=True)


def test_child_system_prompt_is_a_single_mode_free_constant() -> None:
    # The prompt is one constant shared by both arms; it must not speak either
    # arm's execution vocabulary (identical child ⇒ no arm-favouring capability
    # change), while keeping the public /app-exploration preference and the
    # self-check tool guidance.
    prompt = CHILD_SYSTEM_PROMPT.lower()
    for token in ("linear", "async", "bundle", "leaderboard", "occurrence"):
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


def _project_for(scaffold: ReferenceScaffold) -> dict:
    if scaffold.start["execution_mode"] == "linear":
        entries = scaffold.manager.build_linear_bundle()["workstreams"]
        return {entry["workstream_id"]: _normalize_entry(entry) for entry in entries}
    rows = scaffold.manager.statuses()
    return {row["workstream_id"]: _normalize_row(row) for row in rows}


def test_termination_classification_is_identical_across_modes() -> None:
    """Same terminal inputs → same canonical verdicts in both modes; the ONLY
    allowed differences are arrival timing / presentation (async enqueues
    per-result occurrences, linear aggregates one atomic bundle).
    """
    async def exercise() -> None:
        linear = _scaffold(_start("mab-late-test-evidence-7d09ace3d3", "linear"))
        async_ = _scaffold(_start("mab-late-test-evidence-7d09ace3d3", "async"))
        manager = linear.manager
        for scaffold in (linear, async_):
            scaffold.manager._launch_queued = lambda: None
            scaffold.manager.spawn_initial_wave()  # seeds attempt_counts = 1
        # Design one wave child per terminal kind.
        states = {
            "requirement_worker_01": "delivery",
            "requirement_worker_02": "rejection",
            "requirement_worker_03": "resource_exhausted",
            "requirement_worker_04": "timeout",
        }
        for workstream_id, kind in states.items():
            for scaffold in (linear, async_):
                child_id = _child_id_for(scaffold.manager, workstream_id)
                if kind == "delivery":
                    completion_id = _bind_completion(scaffold.manager, child_id)
                    await scaffold.manager.handle_delivery({
                        "completion_id": completion_id, "payload": {"i": 1},
                        "payload_sha256": "a" * 64, "child_id": child_id,
                    })
                elif kind == "rejection":
                    completion_id = _bind_completion(scaffold.manager, child_id)
                    await scaffold.manager.handle_rejection({
                        "completion_id": completion_id,
                        "reason_codes": ["report_file_missing", "report_json_invalid"],
                        "child_id": child_id,
                    })
                elif kind == "resource_exhausted":
                    scaffold.manager.children[child_id].status = "completed_hidden"
                    scaffold.manager.children[child_id].decision = "resource_exhausted"
                else:  # timeout / cancellation path
                    scaffold.manager.children[child_id].status = "cancelled"
                    scaffold.manager.children[child_id].decision = "cancelled"

        linear_verdicts = _project_for(linear)
        async_verdicts = _project_for(async_)
        assert linear_verdicts == async_verdicts
        assert linear_verdicts["requirement_worker_01"] == ("delivered", (), None, None)
        assert linear_verdicts["requirement_worker_02"] == (
            "contract_rejected",
            ("report_file_missing", "report_json_invalid"),
            "report_file",
            1,
        )
        assert linear_verdicts["requirement_worker_03"] == ("completed_hidden", (), None, None)
        assert linear_verdicts["requirement_worker_04"] == ("cancelled", (), None, None)

        # The one allowed difference: async per-result presentation vs the
        # linear atomic bundle.
        assert async_.manager.presentation_queue.has_pending() is True
        assert linear.manager.presentation_queue.has_pending() is False
        assert not any(
            event.get("type") in {"result_presented", "adapter_queued", "result_available"}
            for event in linear.emitter.events
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
