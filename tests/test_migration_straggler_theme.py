"""Task 10 migration conformance for the straggler_under_resource_pressure theme.

The 10 registered cases of this theme author two dual-nature stimuli declared
through the shared ``stimulus_type`` contract:

* ``resource_pressure`` -- as a DELIVERY row on the authority result (tagged
  authority row that reaches the main model only through the gateway) and, in
  a live variant, as a live row fired at the straggler's ``child_started``.
* ``deadline_update`` -- a live row fired once at the first child boundary,
  carrying a numeric ``deadline_wall``.

These tests prove, end-to-end through ``run_episode`` with a scripted adapter
and a minimal case that declares the migrated stimulus shape, that:

* a live ``resource_pressure`` row produces the kernel-private pressure audit
  when its straggler starts;
* a ``resource_pressure``-tagged delivery row is *not* consumed by the live
  seam -- it is held by the schedule and presented to the participant as a
  public ``result_delivered`` message;
* a live ``deadline_update`` row produces the kernel-private deadline audit;
* the migrated schedule shape itself passes the event-taxonomy validator.
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
from async_rbench.evaluation.event_taxonomy import validate_scenario_events
from async_rbench.evaluation.runner import EpisodeConfig
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.spec import discover_cases


ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Minimal runnable case fixture (mirrors the migrated stimulus authoring shape)
# ---------------------------------------------------------------------------


def _write_case(
    tmp_path: Path,
    *,
    case_id: str,
    events: list[dict],
    workstream_ids: list[str] | None = None,
    bindings: dict | None = None,
) -> Path:
    workstream_ids = workstream_ids or ["authority"]
    bindings = dict(bindings or {})
    # Task 4 fail-closed contract: every workstream must declare a validator_stage.
    for stream_id in workstream_ids:
        binding = bindings.setdefault(stream_id, {})
        binding.setdefault("validator_stage", "semantic_evidence")
    case = tmp_path / case_id
    (case / "private").mkdir(parents=True)
    (case / "task" / "tests").mkdir(parents=True)
    (case / "task" / "assets").mkdir(parents=True)
    (case / "public_case.yaml").write_text(yaml.safe_dump({
        "format_version": 2, "case_id": case_id,
        "title": "Declared straggler stimulus",
        "task_instruction_path": "task/task.yaml",
        "workstreams": [{
            "id": stream_id, "task": "recover", "targets": [],
            "expected_output": "out", "priority": "normal",
            "public_result_contract": {"kind": "payload_only"},
        } for stream_id in workstream_ids],
        "artifacts": [],
    }), encoding="utf-8")
    (case / "private/private_case.yaml").write_text(yaml.safe_dump({
        "case_id": case_id,
        "workstream_bindings": bindings,
        "authoritative_result_kind": "result_authority",
        "result_contract": {"allowed_result_kinds": ["result_authority"]},
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
    """The adapter-visible transcript that spawns+starts each (child, workstream).

    ``participant_metadata.config_sha256`` and ``child_spawned.parent_id`` are
    required by ``validate_adapter_event``; omitting them drops the event before
    ``run_episode`` can bind the child to its workstream (see the sibling
    ``test_migration_child_failure_theme`` for the same rationale).
    """
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


# ---------------------------------------------------------------------------
# resource_pressure live row
# ---------------------------------------------------------------------------


def test_run_episode_resource_pressure_live_row_audits_straggler(
    tmp_path: Path, monkeypatch,
) -> None:
    """A live resource_pressure row (no result role) fires at the straggler start.

    The migrated cases declare the live form as a mechanism row keyed on
    ``straggler_child_id``; ``run_episode`` must materialise its audit as a
    kernel-private pressure fact and never as a public delivery.
    """
    case = _write_case(tmp_path, case_id="straggler-live", events=[
        {"id": "evt.pressure.live", "stimulus_type": "resource_pressure",
         "straggler_child_id": "c1", "resource": "concurrency_slot",
         "limit": 1, "pool_remaining": 0,
         "workstream_id": "authority"},
    ], bindings={"authority": {"result_kind": "result_authority"}})
    sink: list[dict] = []
    _patch_live_adapter(monkeypatch, _adapter_events(("c1", "authority")), sink)
    config = _live_episode_config(tmp_path, case, "live-pressure")
    asyncio.run(runner_module.run_episode(ROOT, config))

    facts = [r for r in _trace_rows(tmp_path) if r.get("type") == "resource_pressure"]
    assert facts, "resource_pressure audit never reached the trace"
    assert facts[0]["applied"] is True
    assert facts[0]["straggler_child_id"] == "c1"
    assert facts[0]["resource"] == "concurrency_slot"
    assert facts[0]["concurrency_limit"] == 1
    assert facts[0]["visibility"] == "kernel_private"
    # A live mechanism row is never presented to the participant as a delivery.
    assert all(
        row.get("type") != "result_delivered" or "resource_pressure" not in str(row)
        for row in _trace_rows(tmp_path)
    )


def test_controller_live_pressure_refused_for_non_in_flight_straggler() -> None:
    """A live pressure row fires only for its own straggler, and only in flight.

    Another child's boundary never consumes the row; the straggler's own
    boundary consumes it but the gateway can *prove* the straggler was never in
    flight (the runner records a child before the seam consumes it), so the
    activation is refused and recorded with ``applied: False``.
    """
    controller = DeliveryController("async", {
        "scenarios": {"async": {"events": [
            {"id": "evt.pressure.live", "stimulus_type": "resource_pressure",
             "straggler_child_id": "ghost", "resource": "concurrency_slot",
             "limit": 1, "pool_remaining": 0},
        ]}},
    })
    # Not the designated straggler: nothing is consumed or audited.
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "other",
    }) == []
    assert controller.pressure_audits == []
    # The straggler's own boundary consumes the row, but the straggler was never
    # recorded in flight -> a refused (applied=False) activation audit.
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "ghost",
    }) == []
    assert len(controller.pressure_audits) == 1
    assert controller.pressure_audits[0]["applied"] is False
    assert controller.pressure_audits[0]["straggler_in_flight"] is False
    # Record the child in flight first (as the runner does), and the same row
    # would activate for real -- proving the guard is the in-flight gate.
    controller2 = DeliveryController("async", {
        "scenarios": {"async": {"events": [
            {"id": "evt.pressure.live", "stimulus_type": "resource_pressure",
             "straggler_child_id": "ghost", "resource": "concurrency_slot",
             "limit": 1, "pool_remaining": 0},
        ]}},
    })
    controller2.on_child_started({"type": "child_started", "child_id": "ghost"})
    controller2.consume_declared_stimuli({
        "type": "child_started", "child_id": "ghost",
    })
    assert len(controller2.pressure_audits) == 1
    assert controller2.pressure_audits[0]["applied"] is True


# ---------------------------------------------------------------------------
# resource_pressure delivery row: presented through the gateway, not live
# ---------------------------------------------------------------------------


def test_run_episode_resource_pressure_delivery_row_is_presented_not_consumed_live(
    tmp_path: Path, monkeypatch,
) -> None:
    """A resource_pressure-tagged authority delivery row is governed by _drain.

    The migrated SWE/TBN authority rows carry ``stimulus_type: resource_pressure``
    together with a ``result`` role; ``run_episode`` must hold the authority
    completion and present it to the participant as a public ``result_delivered``
    -- never consuming it through the live pressure seam.
    """
    events = [
        {"id": "evt.pressure.authority", "stimulus_type": "resource_pressure",
         "result": "result_authority", "resource": "concurrency_slot",
         "limit": 1, "workstream_id": "authority"},
    ]
    case = _write_case(
        tmp_path, case_id="straggler-delivery", events=events,
        workstream_ids=["provisional", "authority"],
        bindings={
            "provisional": {"result_kind": "result_provisional"},
            "authority": {"result_kind": "result_authority"},
        },
    )
    sink: list[dict] = []
    transcript = _adapter_events(
        ("ca-authority", "authority"), ("cp-provisional", "provisional"),
    )
    # The authority child completes while both initial children are in flight.
    transcript.append({
        "type": "child_completed", "child_id": "ca-authority",
        "completion_id": "authority-1",
        "result_kind": "result_authority", "payload": {"result": "final"},
    })
    transcript.append({"type": "episode_ended", "final_answer": "done",
                       "local_status": "completed", "declared_task_success": True})
    _patch_live_adapter(monkeypatch, transcript, sink)
    config = _live_episode_config(tmp_path, case, "delivery-pressure")
    asyncio.run(runner_module.run_episode(ROOT, config))

    # The authority result was presented to the participant (public shape: no
    # evaluator result_kind / benchmark_event_id leaks into the message).
    deliveries = [m for m in sink if m.get("type") == "result_delivered"]
    assert deliveries, "authority delivery was never presented to the adapter"
    assert deliveries[-1]["completion_id"] == "authority-1"
    assert deliveries[-1]["payload"] == {"result": "final"}
    assert "result_kind" not in deliveries[-1]

    # The kernel separately records the delivery under the declared stimulus id.
    facts = [
        r for r in _trace_rows(tmp_path)
        if r.get("type") == "result_delivery_evaluator_fact"
    ]
    assert facts, "delivery evaluator fact never reached the trace"
    assert facts[0]["completion_id"] == "authority-1"
    assert facts[0]["result_kind"] == "result_authority"
    assert facts[0]["benchmark_event_id"] == "evt.pressure.authority"

    # The delivery row was *not* consumed by the live pressure seam.
    assert not [
        r for r in _trace_rows(tmp_path) if r.get("type") == "resource_pressure"
    ]


def test_controller_skips_delivery_pressure_row_and_fires_only_live_row() -> None:
    """A schedule may declare pressure in both forms; the seam keeps them apart.

    The delivery row (carrying a ``result`` role) must be ignored by the live
    seam -- it is governed by ``_drain`` -- while the live row (no result)
    fires exactly once when its straggler starts.
    """
    case = {
        "scenarios": {"linear": {"events": []}, "async": {"events": [
            # Delivery form: tagged authority delivery (the migrated rows).
            {"id": "delivery", "stimulus_type": "resource_pressure",
             "result": "authority", "resource": "concurrency_slot",
             "limit": 1, "workstream_id": "authority"},
            # Live form: a separate mechanism row keyed on the straggler child.
            {"id": "live", "stimulus_type": "resource_pressure",
             "straggler_child_id": "c1", "resource": "concurrency_slot",
             "limit": 2, "pool_remaining": 1},
            {"id": "deadline", "stimulus_type": "deadline_update",
             "deadline_wall": 3600.0, "reason": "sla"},
        ]}},
    }
    controller = DeliveryController("async", case)
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    deliveries = controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c1",
    })
    assert deliveries == []
    assert len(controller.pressure_audits) == 1
    assert controller.pressure_audits[0]["applied"] is True
    assert controller.pressure_audits[0]["straggler_child_id"] == "c1"
    assert controller.pressure_audits[0]["resource"] == "concurrency_slot"
    assert len(controller.deadline_audits) == 1
    # Idempotent: no live row fires a second time on another child boundary.
    controller.on_child_started({"type": "child_started", "child_id": "c2"})
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c2",
    }) == []
    assert len(controller.pressure_audits) == 1
    assert len(controller.deadline_audits) == 1


# ---------------------------------------------------------------------------
# deadline_update live row
# ---------------------------------------------------------------------------


def test_run_episode_deadline_update_live_row_audits_deadline(
    tmp_path: Path, monkeypatch,
) -> None:
    """A live deadline_update row (numeric deadline_wall) produces an audit.

    The migrated cases add this row to every authority delivery; it is consumed
    once at the first child boundary and materialised as a kernel-private
    deadline fact carrying the new wall value and reason.
    """
    case = _write_case(tmp_path, case_id="straggler-deadline", events=[
        {"id": "evt.pressure.authority.deadline_update",
         "stimulus_type": "deadline_update", "deadline_wall": 3600.0,
         "reason": "straggler_response_window_deadline",
         "workstream_id": "authority"},
    ], bindings={"authority": {"result_kind": "result_authority"}})
    sink: list[dict] = []
    _patch_live_adapter(monkeypatch, _adapter_events(("c1", "authority")), sink)
    config = _live_episode_config(tmp_path, case, "live-deadline")
    asyncio.run(runner_module.run_episode(ROOT, config))

    facts = [r for r in _trace_rows(tmp_path) if r.get("type") == "deadline_update"]
    assert facts, "deadline_update audit never reached the trace"
    assert facts[0]["after_deadline"] == 3600.0
    assert facts[0]["reason"] == "straggler_response_window_deadline"
    assert facts[0]["visibility"] == "kernel_private"
    assert all(row.get("type") != "deadline_update" for row in sink)


# ---------------------------------------------------------------------------
# migrated schedule shape validates
# ---------------------------------------------------------------------------


def test_migrated_straggler_schedule_shape_validates() -> None:
    """The schedule authoring used by the 10 migrated cases passes the taxonomy.

    Mirrors the MAB form (authority delivery tagged resource_pressure and bound
    after ``after_results``) and the SWE/TBN form (after ``after_artifacts``),
    each plus the added live ``deadline_update`` row.
    """
    common = {
        "allowed_results": {"result_01", "result_02", "result_03", "result_04"},
        "workstream_ids": {"requirement_worker_01", "requirement_worker_02",
                           "requirement_worker_03", "requirement_worker_04"},
        "known_artifacts": {"provisional_checkpoint", "preserved_source_facts",
                            "final_state"},
        "known_milestones": {"consume_async_evidence", "reverify_and_close"},
    }
    mab = [
        {"id": "evt.mab.straggler_under_resource.upstream", "result": "result_01"},
        {"id": "evt.mab.straggler_under_resource", "result": "result_02",
         "stimulus_type": "resource_pressure", "workstream_id": "requirement_worker_02",
         "resource": "concurrency_slot", "limit": 1,
         "trigger": "after_results_delivered", "after_results": ["result_01"]},
        {"id": "evt.mab.straggler_under_resource.deadline_update",
         "stimulus_type": "deadline_update", "workstream_id": "requirement_worker_02",
         "deadline_wall": 3600.0, "reason": "straggler_response_window_deadline"},
    ]
    swe = [
        {"id": "evt.swe.straggler_under_resource.workstream", "result": "result_01"},
        {"id": "evt.swe.straggler_under_resource", "result": "result_02",
         "stimulus_type": "resource_pressure", "workstream_id": "requirement_worker_02",
         "resource": "concurrency_slot", "limit": 1,
         "trigger": "after_artifacts_committed",
         "after_artifacts": ["provisional_checkpoint", "preserved_source_facts"]},
        {"id": "evt.swe.straggler_under_resource.deadline_update",
         "stimulus_type": "deadline_update", "workstream_id": "requirement_worker_02",
         "deadline_wall": 3600.0, "reason": "straggler_response_window_deadline"},
    ]
    assert validate_scenario_events(mab, execution_mode="async", **common) == []
    assert validate_scenario_events(swe, execution_mode="async", **common) == []

    missing_wall = [dict(event) for event in mab]
    missing_wall[-1] = {
        k: v for k, v in missing_wall[-1].items() if k != "deadline_wall"
    }
    errors = validate_scenario_events(missing_wall, execution_mode="async", **common)
    assert any("deadline_update must declare a numeric deadline_wall" in error
               for error in errors)

    non_numeric = [dict(event) for event in mab]
    non_numeric[-1] = {**non_numeric[-1], "deadline_wall": "2026-09-03T00:00:00Z"}
    errors = validate_scenario_events(non_numeric, execution_mode="async", **common)
    assert any("deadline_wall must be numeric" in error for error in errors)


# ---------------------------------------------------------------------------
# Real-case migration data guards (the 10 registered straggler cases)
# ---------------------------------------------------------------------------

SCORE_DOMAINS = frozenset({"base_task", "async_replanning"})
OBSERVATION_FIELDS = (
    "required_changes",
    "required_preservation",
    "forbidden_changes",
    "closure_checks",
    "expected_disposition",
    "event_status",
)

EXPECTED_STRAAGGLER_DIRS = frozenset({
    "mab-dependency-unblock-0daa930906",
    "mab-dependency-unblock-3005dbb57f",
    "mab-dependency-unblock-8d29bb0513",
    "mab-dependency-unblock-9739b40e89",
    "mab-late-constraint-203f5009fd",
    "swe-dependency-unblock-3361c7af50",
    "swe-dependency-unblock-8902c7f431",
    "swe-late-constraint-3950516755",
    "swe-late-constraint-7ce47cda27",
    "tbn-late-test-evidence-9685a54f22",
})


def _straggler_cases() -> list[Path]:
    """The registered case dirs whose primary_event_theme is straggler."""
    cases = []
    for case in discover_cases(ROOT):
        private = yaml.safe_load(
            (case.case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        theme = ((private.get("classification") or {}).get("primary_event_theme") or "")
        if theme == "straggler_under_resource_pressure":
            cases.append(case.case_dir)
    return sorted(cases)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_lane_targets_the_ten_registered_straggler_cases() -> None:
    assert {case_dir.name for case_dir in _straggler_cases()} == EXPECTED_STRAAGGLER_DIRS


def test_every_straggler_case_check_has_exactly_one_scoring_domain() -> None:
    """Each migrated semantic check carries exactly one resolvable score_domain."""
    for case_dir in _straggler_cases():
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
            if domain == "async_replanning":
                event_id = str(check.get("event_id") or "")
                assert event_id in contract_event_ids, (
                    case_dir.name, check_id, event_id, contract_event_ids,
                )
            elif check.get("event_id") is not None:
                raise AssertionError((case_dir.name, check_id, "base_task carried event_id"))


def test_every_straggler_case_event_contract_carries_observation_fields(
) -> None:
    """The six observation fields are non-empty on all three mirrors and equal.

    The private top-level ``event_contracts``, the control-flow evaluator
    registry and the dynamic-point-plan ledger must agree, and every
    ``closure_checks`` reference must resolve to an actual semantic check id --
    the guard that caught the original dash-form (directory-name) reference,
    which silently pinned the closure component at 0.0.
    """
    for case_dir in _straggler_cases():
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        ledger = _load(case_dir / "private" / "dynamic_point_plan.json")
        private = _load(case_dir / "private" / "private_case.yaml")
        semantic_ids = {str(check["id"]) for check in semantic["checks"]}
        assert semantic_ids

        contracts = control.get("event_contracts") or []
        assert contracts, case_dir.name
        for contract in contracts:
            missing = [field for field in OBSERVATION_FIELDS if field not in contract]
            assert not missing, (case_dir.name, contract.get("event_id"), missing)
            assert isinstance(contract.get("required_changes"), list) and contract["required_changes"]
            assert isinstance(contract.get("required_preservation"), list) and contract["required_preservation"]
            assert isinstance(contract.get("forbidden_changes"), list)
            assert contract.get("closure_checks"), (case_dir.name, contract.get("event_id"))
            assert str(contract.get("expected_disposition") or "").strip()
            assert contract.get("event_status") == "scored"
            # Every closure reference must resolve to a real semantic check id
            # (the underscore-form `{case}.closure` in semantic_checks.json).
            refs = {str(item) for item in contract.get("closure_checks")}
            assert refs <= semantic_ids, (case_dir.name, refs - semantic_ids)
            assert any(str(item).endswith(".closure") for item in refs)

        # The three mirrors agree on the observation contract.
        assert ledger == control, case_dir.name
        assert private.get("event_contracts") == contracts, case_dir.name


def test_real_straggler_case_closure_component_scores_full_value() -> None:
    """The real underscore closure id yields a full closure score, not 0.0.

    ``_closure_score`` joins semantic results by exact check id. The migrated
    cases reference ``{underscore_case}.closure`` (the real semantic check); when
    that check passes the closure component must be 1.0 and add its quarter to
    the process score. A directory-name (dash-form) reference would silently
    resolve to nothing and return 0.0 -- the regression this lane's first pass
    shipped and the reviewer rejected.
    """
    case_dir = _straggler_cases()[0]
    control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
    semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
    contracts = control.get("event_contracts") or []
    assert len(contracts) == 1
    contract = contracts[0]

    # A faithful "perfect episode" result set: every real semantic check passed.
    perfect_results = [{**check, "passed": True} for check in semantic["checks"]]

    closure = _closure_score(contract, perfect_results)
    assert closure == 1.0, (case_dir.name, contract.get("closure_checks"), closure)

    event_drs = score_event_replanning(
        contract, before=None, after=None, semantic_results=perfect_results,
    )
    assert event_drs.component_scores["closure"] == 1.0
    assert event_drs.async_outcome == 1.0
    assert event_drs.process_score is not None

    # Negative control: the dash-form reference the first pass wrote resolves to
    # nothing (no semantic check has that id), so closure collapses to 0.0.
    dash_contract = dict(contract)
    dash_contract["closure_checks"] = [f"{case_dir.name}.closure"]
    assert {str(item) for item in dash_contract["closure_checks"]} & {
        str(check["id"]) for check in semantic["checks"]
    } == set()
    assert _closure_score(dash_contract, perfect_results) == 0.0
    dash_drs = score_event_replanning(
        dash_contract, before=None, after=None, semantic_results=perfect_results,
    )
    assert dash_drs.component_scores["closure"] == 0.0
    assert event_drs.process_score == dash_drs.process_score + 0.25
    assert event_drs.total == dash_drs.total + 0.125
