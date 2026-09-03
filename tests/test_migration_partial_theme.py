"""Migration guards for the ``partial_then_complete_result`` swimlane (Task 10).

The lane migrates the 24 cases whose ``primary_event_theme`` is
``partial_then_complete_result`` to the new event contract:

* every semantic check is tagged with exactly one ``score_domain``
  (``base_task`` | ``async_replanning``); an ``async_replanning`` check binds the
  theme's authority scenario event id, while ``relevance_tier`` is retained.
* the control-flow registry's ``event_contracts`` observation contract expresses
  the partial-then-complete resolution (the partial result is presented first
  and is later superseded by the complete authority, which invalidates the final
  artifact and reopens the reverify milestones) via ``required_changes`` /
  ``required_preservation`` / ``forbidden_changes`` / ``closure_checks`` /
  ``expected_disposition`` / ``event_status``.

The runtime half drives the DeliveryController and ``run_episode`` and asserts
the theme semantics the migrated data describes: the partial result is presented
before the complete authority (a FIFO/window guarantee that holds even when the
authority completion arrives first), the authority superseding delivery is one
fresh occurrence carrying its ``invalidates_artifacts`` / ``reopens_milestones``,
and a superseded partial that arrives after the complete authority is stale.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml

import async_rbench.evaluation.runner as runner_module
from async_rbench.evaluation.control_flow_gates import (
    _closure_score,
    score_event_replanning,
)
from async_rbench.evaluation.runner import EpisodeConfig
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.spec import discover_cases

ROOT = Path(__file__).resolve().parents[1]
SCORE_DOMAINS = frozenset({"base_task", "async_replanning"})
OBSERVATION_FIELDS = (
    "required_changes",
    "required_preservation",
    "forbidden_changes",
    "closure_checks",
    "expected_disposition",
    "event_status",
)
V7_DISPOSITION = "adopt_complete_authority_and_supersede_partial_result"

EXPECTED_PARTIAL_DIRS = frozenset({
    "data-recovery-service",
    "mab-cross-app-artifact-7bfdfeaa3c",
    "mab-dependency-unblock-0d4cb0c77d",
    "mab-dependency-unblock-1247bebf08",
    "mab-dependency-unblock-593d775fd8",
    "mab-dependency-unblock-7e90efa752",
    "mab-dependency-unblock-a36888cf46",
    "mab-dependency-unblock-c27563df83",
    "mab-dependency-unblock-cb636c66eb",
    "mab-dependency-unblock-fe0736601e",
    "osw-cross-app-artifact-2a25ab8769",
    "osw-cross-app-artifact-6dec97765d",
    "osw-cross-app-artifact-8e188f4a86",
    "osw-cross-app-artifact-f96bcb2739",
    "osw-dependency-unblock-346b788fd5",
    "osw-dependency-unblock-a37e5099b4",
    "osw-state-reconciliation-6f2dfbe1f4",
    "osw-state-reconciliation-8fec3dd813",
    "swe-bench-selective-patch",
    "swe-dependency-unblock-3f6d310987",
    "swe-dependency-unblock-d7e3da4ccb",
    "swe-late-constraint-17e23e3eb3",
    "tbn-conflicting-specialist-results-a76a766789",
    "tbn-conflicting-specialist-results-f3324bac38",
})


def _partial_cases() -> list[Path]:
    cases = []
    for case in discover_cases(ROOT):
        private = yaml.safe_load(
            (case.case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        theme = ((private.get("classification") or {}).get("primary_event_theme") or "")
        if theme == "partial_then_complete_result":
            cases.append(case.case_dir)
    return sorted(cases)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Migration data guards
# ---------------------------------------------------------------------------


def test_lane_targets_the_24_registered_partial_cases() -> None:
    target_dirs = {case_dir.name for case_dir in _partial_cases()}
    assert target_dirs == EXPECTED_PARTIAL_DIRS


def test_every_partial_case_check_has_exactly_one_scoring_domain() -> None:
    """Each migrated semantic check carries exactly one resolvable score_domain.

    ``base_task`` iff the check targets the frozen base completion; every other
    check is ``async_replanning`` and must bind a real event-contract id so the
    event's AsyncOutcome can route to it. ``relevance_tier`` is retained.
    """
    for case_dir in _partial_cases():
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        contract_event_ids = {
            str(contract.get("event_id"))
            for contract in (control.get("event_contracts") or [])
            if contract.get("event_id")
        }
        assert contract_event_ids, case_dir.name
        for check in semantic["checks"]:
            check_id = str(check["id"])
            domain = check.get("score_domain")
            assert domain in SCORE_DOMAINS, (case_dir.name, check_id, domain)
            assert "relevance_tier" in check, (case_dir.name, check_id)
            is_base = str(check.get("capability_target") or "") == "base_task_completion"
            if domain == "base_task":
                assert is_base, (case_dir.name, check_id, "base_task on a non-base capability")
                assert check.get("event_id") is None, (
                    case_dir.name, check_id, "base_task carried event_id",
                )
            else:
                assert not is_base, (case_dir.name, check_id, "base capability tagged async")
                event_id = str(check.get("event_id") or "")
                assert event_id in contract_event_ids, (
                    case_dir.name, check_id, event_id, contract_event_ids,
                )


def test_every_partial_case_event_contract_carries_observation_fields() -> None:
    """The six observation fields are present and equal across the mirrors.

    The private top-level ``event_contracts``, the control-flow evaluator
    registry and the dynamic-point-plan ledger must agree, and every
    ``closure_checks`` reference must resolve to a real semantic check id.  The
    v7 authority event invalidates the final artifact and reopens milestones;
    the authority's expected disposition is the frozen theme string.
    """
    for case_dir in _partial_cases():
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        private = yaml.safe_load(
            (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        ledger_path = case_dir / "private" / "dynamic_point_plan.json"
        is_v7 = ledger_path.exists()
        semantic_ids = {str(check["id"]) for check in semantic["checks"]}
        assert semantic_ids

        contracts = control.get("event_contracts") or []
        assert contracts, case_dir.name
        for contract in contracts:
            missing = [field for field in OBSERVATION_FIELDS if field not in contract]
            assert not missing, (case_dir.name, contract.get("event_id"), missing)
            assert isinstance(contract.get("required_changes"), list) and contract["required_changes"]
            assert isinstance(contract.get("required_preservation"), list)
            assert isinstance(contract.get("forbidden_changes"), list)
            assert contract.get("closure_checks"), (case_dir.name, contract.get("event_id"))
            refs = {str(item) for item in contract.get("closure_checks")}
            assert refs <= semantic_ids, (case_dir.name, refs - semantic_ids)
            assert str(contract.get("expected_disposition") or "").strip()
            assert contract.get("event_status") == "scored"

        if is_v7:
            # Three-way mirror parity plus the theme shape on the authority event.
            ledger = _load(ledger_path)
            assert ledger == control, case_dir.name
            private_contracts = private.get("event_contracts") or []
            assert private_contracts == contracts, case_dir.name
            authoritative = str(private.get("authoritative_result_kind") or "")
            assert authoritative, case_dir.name
            events = (private.get("scenarios") or {}).get("async", {}).get("events") or []
            authority_events = [
                event for event in events
                if str(event.get("result") or "") == authoritative
            ]
            assert len(authority_events) == 1, (case_dir.name, authoritative)
            authority_event = authority_events[0]
            assert authority_event.get("invalidates_artifacts") == ["final_state"], (
                case_dir.name, authority_event.get("invalidates_artifacts"),
            )
            assert authority_event.get("reopens_milestones"), (case_dir.name, authority_event)
            assert contract["expected_disposition"] == V7_DISPOSITION, case_dir.name


# ---------------------------------------------------------------------------
# Real-case closure component resolves to a full value (not a silent 0.0)
# ---------------------------------------------------------------------------


def test_real_partial_case_closure_component_scores_full_value() -> None:
    """The migrated underscore closure ids yield a full closure score.

    ``_closure_score`` joins semantic results by exact check id.  The migrated
    v7 cases reference ``{underscore_case}.closure`` (and the base
    ``.source.event_closure`` mirror when present) -- real semantic checks.  When
    every check passes the closure component must be 1.0; a directory-name
    (dash-form) reference would silently resolve to nothing and return 0.0, the
    regression this lane's guard exists to catch.
    """
    for case_dir in _partial_cases():
        ledger_path = case_dir / "private" / "dynamic_point_plan.json"
        if not ledger_path.exists():
            continue  # legacy v3/v4 cases keep a control-only minimal event contract.
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        contracts = control.get("event_contracts") or []
        assert len(contracts) == 1
        contract = contracts[0]
        perfect_results = [{**check, "passed": True} for check in semantic["checks"]]
        assert _closure_score(contract, perfect_results) == 1.0, case_dir.name
        event_drs = score_event_replanning(
            contract, before=None, after=None, semantic_results=perfect_results,
        )
        assert event_drs.component_scores["closure"] == 1.0
        assert event_drs.async_outcome == 1.0
        assert event_drs.process_score is not None
        dash_contract = dict(contract)
        dash_contract["closure_checks"] = [f"{case_dir.name}.closure"]
        assert {str(item) for item in dash_contract["closure_checks"]} & {
            str(check["id"]) for check in semantic["checks"]
        } == set()
        assert _closure_score(dash_contract, perfect_results) == 0.0


# ---------------------------------------------------------------------------
# Runtime theme semantics (partial-then-complete at the DeliveryController)
# ---------------------------------------------------------------------------


def _base_case(events: list[dict], stale_predicate: dict | None = None) -> dict:
    return {
        "authoritative_result_kind": "complete",
        "superseded_result_kind": "partial",
        "stale_predicate": stale_predicate,
        "result_contract": {"allowed_result_kinds": ["partial", "complete"]},
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": events},
        },
    }


def _completion(child_id: str, completion_id: str, result_kind: str, payload: dict) -> dict:
    return {
        "type": "child_completed",
        "child_id": child_id,
        "completion_id": completion_id,
        "result_kind": result_kind,
        "payload": payload,
    }


def _partial_complete_events() -> list[dict]:
    """Partial result delivered immediately; complete authority waits for it."""
    return [
        {"id": "evt.partial", "result": "partial"},
        {"id": "evt.complete", "result": "complete",
         "trigger": "after_results_delivered", "after_results": ["partial"],
         "invalidates_artifacts": ["final_state"],
         "reopens_milestones": ["consume_async_evidence", "reverify_and_close"]},
    ]


def test_partial_is_presented_before_complete_authority_in_natural_order() -> None:
    """A partial result that completes first is delivered as its own occurrence.

    The complete authority that follows is a second, distinct occurrence carrying
    the superseding invalidation/reopen set -- it never displaces the already
    presented partial record but supersedes it in state.
    """
    controller = DeliveryController("async", _base_case(_partial_complete_events()))
    controller.spawned = {"c1": {}, "c2": {}}
    partial = controller.on_complete(
        _completion("c1", "partial-1", "partial", {"result": "draft"})
    )
    assert len(partial) == 1
    assert partial[0]["result_kind"] == "partial"
    assert partial[0]["stale"] is False
    assert partial[0]["invalidates_artifacts"] == []
    partial_occurrence = partial[0]["delivery_occurrence_id"]

    complete = controller.on_complete(
        _completion("c2", "complete-1", "complete", {"result": "final"})
    )
    assert len(complete) == 1
    message = complete[0]
    assert message["result_kind"] == "complete"
    assert message["stale"] is False
    assert message["invalidates_artifacts"] == ["final_state"]
    assert message["reopens_milestones"] == ["consume_async_evidence", "reverify_and_close"]
    assert message["delivery_occurrence_id"] != partial_occurrence
    assert controller.delivery_order == ["partial-1", "complete-1"]


def test_complete_authority_is_held_until_partial_is_presented() -> None:
    """FIFO/window correctness: the authority can never jump the partial.

    Even when the complete-authority completion arrives first, the partial result
    has not yet been presented, so the authority is held; once the partial is
    presented both are released in partial-then-complete order (never the other
    way round).
    """
    controller = DeliveryController("async", _base_case(_partial_complete_events()))
    controller.spawned = {"c1": {}, "c2": {}}
    # The authority completion arrives first; its window is not open because the
    # partial has not been presented.  Nothing is delivered.
    early = controller.on_complete(
        _completion("c1", "complete-1", "complete", {"result": "final"})
    )
    assert early == []
    # The partial now arrives: both results are released in presentation order.
    released = controller.on_complete(
        _completion("c2", "partial-1", "partial", {"result": "draft"})
    )
    assert [message.get("result_kind") for message in released] == ["partial", "complete"]
    assert [message.get("stale") for message in released] == [False, False]
    assert controller.delivery_order == ["partial-1", "complete-1"]


def test_late_superseded_partial_is_stale_after_complete_authority() -> None:
    """Once the complete authority is delivered, a late partial is evaluator-stale.

    The superseded partial that arrives late (a different revision) can no longer
    be presented as the current truth: only the complete authority is.
    """
    controller = DeliveryController("async", _base_case(
        _partial_complete_events(),
        stale_predicate={
            "type": "revision_mismatch",
            "authoritative_fields": ["fix_revision"],
            "superseded_fields": ["run_revision"],
        },
    ))
    controller.spawned = {"c1": {}, "c2": {}}
    partial = controller.on_complete(
        _completion("c1", "partial-1", "partial", {"evidence": {"run_revision": "R1"}})
    )
    complete = controller.on_complete(
        _completion("c2", "complete-1", "complete", {"evidence": {"fix_revision": "R2"}})
    )
    assert partial and complete
    assert partial[0]["stale"] is False
    assert complete[0]["stale"] is False
    late = controller.on_complete(
        _completion("c3", "partial-late", "partial", {"evidence": {"run_revision": "R9"}})
    )
    assert late
    message = late[0]
    assert message["result_kind"] == "partial"
    assert message["stale"] is True
    assert message["evaluator_stale"] is True
    assert message["evaluator_stale_measurable"] is True
    assert message["evaluator_stale_reason"] == "run_revision=R9 != fix_revision=R2"
    assert controller.delivery_order == ["partial-1", "complete-1", "partial-late"]


# ---------------------------------------------------------------------------
# Runtime theme semantics end-to-end through run_episode
# ---------------------------------------------------------------------------


def _write_partial_case(tmp_path: Path, *, case_id: str, events: list[dict]) -> Path:
    """Write a minimal runnable partial-then-complete case (two workstreams)."""
    case = tmp_path / case_id
    (case / "private").mkdir(parents=True)
    (case / "task" / "tests").mkdir(parents=True)
    (case / "task" / "assets").mkdir(parents=True)
    (case / "public_case.yaml").write_text(yaml.safe_dump({
        "format_version": 2, "case_id": case_id,
        "title": "Declared partial-then-complete result",
        "task_instruction_path": "task/task.yaml",
        "workstreams": [{
            "id": stream_id, "task": "recover", "targets": [],
            "expected_output": "out", "priority": "normal",
            "public_result_contract": {"kind": "payload_only"},
        } for stream_id in ("partial", "complete")],
        "artifacts": [],
    }), encoding="utf-8")
    (case / "private/private_case.yaml").write_text(yaml.safe_dump({
        "case_id": case_id,
        "authoritative_result_kind": "complete",
        "superseded_result_kind": "partial",
        "result_contract": {"allowed_result_kinds": ["partial", "complete"]},
        # Task 4 fail-closed contract: every workstream declares a validator_stage.
        "workstream_bindings": {
            "partial": {"result_kind": "partial", "validator_stage": "semantic_evidence"},
            "complete": {"result_kind": "complete", "validator_stage": "semantic_evidence"},
        },
        "scenarios": {"linear": {"events": []}, "async": {"events": events}},
    }), encoding="utf-8")
    (case / "task/task.yaml").write_text(yaml.safe_dump({
        "instruction": "Recover the state.",
    }), encoding="utf-8")
    (case / "task/run-tests.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (case / "task/tests/semantic_checks.json").write_text(
        json.dumps({"checks": []}), encoding="utf-8")
    (case / "task/tests/control_flow_checks.json").write_text(
        json.dumps({"version": "1", "checks": []}), encoding="utf-8")
    return case


class _FakeLiveAdapter:
    """A scripted adapter process whose stdin writes are captured to ``sink``."""

    def __init__(self, events: list[dict], sink: list[dict]) -> None:
        self.events = events
        self.sink = sink

        class _Stdin:
            def write(self, payload: bytes) -> None:
                sink.append(json.loads(payload))

            async def drain(self) -> None:
                return None

        self.stdin = _Stdin()
        self.stderr = asyncio.StreamReader()
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(
            b"".join(json.dumps(event).encode() + b"\n" for event in events)
        )
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self.returncode = 0

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _patch_live_adapter(monkeypatch, events: list[dict], sink: list[dict]) -> None:
    monkeypatch.setattr(
        runner_module, "_docker",
        lambda *_a, **_k: __import__("types").SimpleNamespace(stdout="", returncode=0),
    )
    monkeypatch.setattr(
        runner_module, "build_workspace_runtime",
        lambda *_a, **_k: DisabledWorkspaceRuntime(),
    )

    async def _spawn(*_a, **_k) -> _FakeLiveAdapter:
        return _FakeLiveAdapter(events, sink)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)


def _adapter_events(*streams: tuple[str, str]) -> list[dict]:
    """The adapter-visible transcript that spawns+starts each (child, workstream)."""
    stream = [
        {"type": "participant_metadata", "backend": "scripted_test",
         "main_model": "scripted-main", "child_model": "scripted-child",
         "workspace_mode": "container_clone",
         "config_sha256": "0123456789abcdef0123456789abcdef"},
        {"type": "ready"},
    ]
    for child_id, workstream_id in streams:
        stream.append({"type": "child_spawned", "child_id": child_id,
                       "parent_id": "main", "work_units": [workstream_id]})
    for child_id, _workstream_id in streams:
        stream.append({"type": "child_started", "child_id": child_id})
    return stream


def _live_episode_config(tmp_path: Path, case_dir: Path, episode_id: str) -> EpisodeConfig:
    return EpisodeConfig(
        episode_id=episode_id, case_id=case_dir.name,
        execution_mode="async", guidance="incentive", agent_seed=1,
        adapter_command=["fake-adapter"], output_dir=tmp_path / "out",
        use_container=False, timeout_sec=10,
        case_dir_override=case_dir,
    )


def _trace_rows(tmp_path: Path) -> list[dict]:
    trace = (tmp_path / "out" / "trace.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in trace.splitlines() if line.strip()]


def test_run_episode_partial_then_complete_supersedes_through_gateway(
    tmp_path: Path, monkeypatch,
) -> None:
    """run_episode presents the partial first, then the superseding authority.

    The kernel records two distinct delivery occurrences: the partial result
    (immediate row) then the complete authority (released once the partial is in
    the delivered set), the authority carrying its ``final_state`` invalidation
    and reverify reopens.  Both reach the participant as public deliveries with
    the partial presented before the complete authority.
    """
    events = _partial_complete_events()
    case = _write_partial_case(tmp_path, case_id="partial-complete-e2e", events=events)
    sink: list[dict] = []
    transcript = _adapter_events(("c-partial", "partial"), ("c-complete", "complete"))
    # The complete-authority child actually finishes before the partial child;
    # the gateway must hold it until the partial result is presented.
    transcript.append({
        "type": "child_completed", "child_id": "c-complete",
        "completion_id": "complete-1", "payload": {"result": "final"},
    })
    transcript.append({
        "type": "child_completed", "child_id": "c-partial",
        "completion_id": "partial-1", "payload": {"result": "draft"},
    })
    transcript.append({"type": "episode_ended", "final_answer": "done",
                       "local_status": "completed", "declared_task_success": True})
    _patch_live_adapter(monkeypatch, transcript, sink)
    config = _live_episode_config(tmp_path, case, "partial-complete-e2e")
    asyncio.run(runner_module.run_episode(ROOT, config))

    facts = [r for r in _trace_rows(tmp_path)
             if r.get("type") == "result_delivery_evaluator_fact"]
    assert len(facts) == 2, [r.get("completion_id") for r in facts]
    partial_fact, complete_fact = facts
    assert partial_fact["completion_id"] == "partial-1"
    assert partial_fact["result_kind"] == "partial"
    assert partial_fact["benchmark_event_id"] == "evt.partial"
    assert partial_fact["stale"] is False
    assert partial_fact["invalidates_artifacts"] == []
    assert complete_fact["completion_id"] == "complete-1"
    assert complete_fact["result_kind"] == "complete"
    assert complete_fact["benchmark_event_id"] == "evt.complete"
    assert complete_fact["stale"] is False
    assert complete_fact["invalidates_artifacts"] == ["final_state"]
    assert complete_fact["reopens_milestones"] == [
        "consume_async_evidence", "reverify_and_close",
    ]
    assert complete_fact["delivery_occurrence_id"] != partial_fact["delivery_occurrence_id"]
    assert partial_fact["delivery_occurrence_id"].startswith("gateway-occ-")

    # Public delivery order: partial presented before the complete authority.
    public = [m for m in sink if m.get("type") == "result_delivered"]
    assert [d["completion_id"] for d in public] == ["partial-1", "complete-1"]
    assert all("result_kind" not in d for d in public)

    # The authority was genuinely held until the partial result was presented.
    held = [r for r in _trace_rows(tmp_path) if r.get("type") == "result_held"]
    assert [h["completion_id"] for h in held] == ["complete-1"]
