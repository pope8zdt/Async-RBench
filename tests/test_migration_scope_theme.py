"""Task 10 migration conformance for the task_scope_or_dependency_change theme.

The 38 migrated cases of this theme (registered instances 39, of which the
legacy ``gaia2-stockholm-moveout`` is a v4 control-flow case left untouched)
author the revision stimulus through the shared ``stimulus_type`` contract:

* ``task_scope_revision`` -- 36 of the 38 tagged authority events, plus
* ``dependency_graph_revision`` -- the remaining 2 dependency-class authorities.

Every migrated event is *dual-nature*: the revision kind is stamped on a
result-bearing authority row (``result_02`` in the SWE/TBN after_artifacts
form, ``result_04`` in the MAB after_results form).  A row with a ``result``
role is a **delivery row** -- it is governed by ``_drain`` and must never be
consumed by the live ``consume_declared_stimuli`` seam.  A row with no result
role is a **live row** fired once at the first child boundary.

These tests prove, end-to-end through ``run_episode`` with a scripted adapter
and a minimal case that declares the migrated stimulus shape, that:

* a ``task_scope_revision`` delivery row reaches the participant as a public
  ``result_delivered`` message carrying the tagged benchmark event id, and is
  *not* consumed by the live revision seam;
* a ``dependency_graph_revision`` delivery row does the same;
* a live (result-less) ``task_scope_revision`` row is consumed once by the
  seam and materialised as a kernel-private revision audit -- never presented
  to the participant;
* every migrated case carries exactly one ``score_domain`` per semantic check,
  binds ``event_id`` for async checks, and its event contract expresses the
  revision observation contract.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml

import async_rbench.evaluation.runner as runner_module
from async_rbench.evaluation.event_taxonomy import validate_scenario_events
from async_rbench.evaluation.runner import EpisodeConfig
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime

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

# The 38 migrated v7 cases.  gaia2-stockholm-moveout is the theme's 39th
# registered instance but a legacy v4 case with no event_contracts / dynamic
# point plan, so it is audited elsewhere and excluded from the v7 migration.
EXPECTED_MIGRATED_DIRS = frozenset({
    "mab-cross-app-artifact-496566389d",
    "mab-cross-app-artifact-4e6f0120bd",
    "mab-cross-app-artifact-b5a48861d5",
    "mab-dependency-unblock-107bc4fe3f",
    "mab-dependency-unblock-19d693bd13",
    "mab-dependency-unblock-71568ae6c9",
    "mab-late-constraint-024b5afe02",
    "mab-late-constraint-02f32d73a5",
    "mab-late-constraint-13dc7627a3",
    "mab-late-constraint-32f347d363",
    "mab-late-constraint-3aa3bf3cca",
    "mab-late-constraint-3c40bbec7f",
    "mab-late-constraint-53ea21919b",
    "mab-late-constraint-5837bf15f5",
    "mab-late-constraint-5aedbb79af",
    "mab-late-constraint-637224fe05",
    "mab-late-constraint-79372889b3",
    "mab-late-constraint-8fc2ddf86a",
    "mab-late-constraint-9636e9ce85",
    "mab-late-constraint-a1b76b3745",
    "mab-late-constraint-fc88525ce2",
    "osw-cross-app-artifact-81b4557778",
    "osw-cross-app-artifact-c3093402e5",
    "swe-dependency-unblock-126ea8db6f",
    "swe-dependency-unblock-16b0d42106",
    "swe-dependency-unblock-470ff65add",
    "swe-dependency-unblock-58ecc4be05",
    "swe-dependency-unblock-866543c501",
    "swe-dependency-unblock-db84717172",
    "swe-late-constraint-148b2c69f6",
    "swe-late-constraint-20b0004f10",
    "swe-late-constraint-6294af1554",
    "swe-late-test-evidence-345fb5c6a6",
    "swe-late-test-evidence-7fb60adc40",
    "swe-late-test-evidence-cb3e057923",
    "tbn-late-test-evidence-30aa2ad8de",
    "tbn-late-test-evidence-78752cd5a1",
    "tbn-partial-failure-recovery-0e92790bd0",
})

ASYNC_CAPABILITIES = frozenset({
    "async_result_integration", "async_consistency_closure",
    "async_dynamic_replanning",
})


def _theme_case_dirs() -> list[Path]:
    from async_rbench.spec import discover_cases
    return sorted(
        case.case_dir
        for case in discover_cases(ROOT)
        if (case.raw.get("classification") or {}).get("primary_event_theme")
        == "task_scope_or_dependency_change"
        and case.case_dir.name != "gaia2-stockholm-moveout"
    )


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Migration data guards over the 38 migrated v7 cases
# ---------------------------------------------------------------------------


def test_lane_targets_the_38_migrated_scope_cases() -> None:
    target_dirs = {case_dir.name for case_dir in _theme_case_dirs()}
    assert target_dirs == EXPECTED_MIGRATED_DIRS


def test_every_scope_case_check_has_exactly_one_scoring_domain() -> None:
    for case_dir in _theme_case_dirs():
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
            # relevance_tier is deliberately retained in the migrated file.
            assert "relevance_tier" in check, (case_dir.name, check_id)
            capability = str(check.get("capability_target") or "")
            if domain == "async_replanning":
                event_id = str(check.get("event_id") or "")
                assert event_id in contract_event_ids, (
                    case_dir.name, check_id, event_id, contract_event_ids,
                )
                assert capability in ASYNC_CAPABILITIES, (
                    case_dir.name, check_id, capability,
                )
            else:
                assert capability not in ASYNC_CAPABILITIES, (
                    case_dir.name, check_id, capability,
                )
                assert check.get("event_id") is None, (
                    case_dir.name, check_id, "base_task carried event_id",
                )


def test_every_scope_case_event_contract_carries_observation_fields() -> None:
    for case_dir in _theme_case_dirs():
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        contracts = control.get("event_contracts") or []
        assert contracts, case_dir.name
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        semantic_ids = {str(c["id"]) for c in semantic["checks"]}
        for contract in contracts:
            missing = [field for field in OBSERVATION_FIELDS if field not in contract]
            assert not missing, (case_dir.name, contract.get("event_id"), missing)
            assert isinstance(contract.get("required_changes"), list)
            assert isinstance(contract.get("required_preservation"), list)
            assert isinstance(contract.get("forbidden_changes"), list)
            closure_ids = contract.get("closure_checks") or []
            assert closure_ids, (case_dir.name, contract.get("event_id"))
            for closure_id in closure_ids:
                assert closure_id in semantic_ids, (
                    case_dir.name, closure_id,
                )
            assert str(contract.get("expected_disposition") or "").strip()
            assert contract.get("event_status") == "scored"
        # The private design ledger mirrors the evaluator registry.
        ledger = _load(case_dir / "private" / "dynamic_point_plan.json")
        assert ledger == control, case_dir.name


def test_every_scope_case_authority_event_declares_the_revision_stimulus() -> None:
    for case_dir in _theme_case_dirs():
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        event_id = control["event_contracts"][0]["event_id"]
        private = yaml.safe_load(
            (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        events = (private.get("scenarios") or {}).get("async", {}).get("events", [])
        main = next((e for e in events if e.get("id") == event_id), None)
        assert main is not None, (case_dir.name, event_id)
        kind = str(main.get("stimulus_type") or "")
        assert kind in {"task_scope_revision", "dependency_graph_revision"}, (
            case_dir.name, kind,
        )
        # Dual-nature authority: a result-bearing delivery row, not a live row.
        assert main.get("result") is not None, (case_dir.name, event_id)


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
        "title": "Declared scope stimulus",
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


# ---------------------------------------------------------------------------
# task_scope_revision delivery row (SWE/TBN authority, 36 migrated cases)
# ---------------------------------------------------------------------------


def test_run_episode_scope_revision_delivery_row_is_presented_not_consumed_live(
    tmp_path: Path, monkeypatch,
) -> None:
    """A task_scope_revision-tagged authority delivery row is governed by _drain.

    The migrated SWE/TBN authority rows carry ``stimulus_type:
    task_scope_revision`` together with a ``result`` role; ``run_episode`` must
    present the authority completion to the participant as a public
    ``result_delivered`` under the tagged event id -- never consuming it through
    the live revision seam.
    """
    events = [
        {"id": "evt.swe.scope_revision", "stimulus_type": "task_scope_revision",
         "result": "result_authority", "workstream_id": "authority"},
    ]
    case = _write_case(
        tmp_path, case_id="scope-delivery", events=events,
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
    transcript.append({
        "type": "child_completed", "child_id": "ca-authority",
        "completion_id": "authority-1",
        "result_kind": "result_authority", "payload": {"result": "final"},
    })
    transcript.append({"type": "episode_ended", "final_answer": "done",
                       "local_status": "completed", "declared_task_success": True})
    _patch_live_adapter(monkeypatch, transcript, sink)
    config = _live_episode_config(tmp_path, case, "delivery-scope")
    asyncio.run(runner_module.run_episode(ROOT, config))

    # The authority result was presented to the participant (public shape: no
    # evaluator result_kind / benchmark_event_id leaks into the message).
    deliveries = [m for m in sink if m.get("type") == "result_delivered"]
    assert deliveries, "authority delivery was never presented to the adapter"
    assert deliveries[-1]["completion_id"] == "authority-1"
    assert deliveries[-1]["payload"] == {"result": "final"}
    assert "result_kind" not in deliveries[-1]

    # The kernel records the delivery under the declared stimulus id.
    facts = [
        r for r in _trace_rows(tmp_path)
        if r.get("type") == "result_delivery_evaluator_fact"
    ]
    assert facts, "delivery evaluator fact never reached the trace"
    assert facts[0]["completion_id"] == "authority-1"
    assert facts[0]["result_kind"] == "result_authority"
    assert facts[0]["benchmark_event_id"] == "evt.swe.scope_revision"

    # The delivery row was *not* consumed by the live revision seam.
    assert not [
        r for r in _trace_rows(tmp_path) if r.get("type") == "task_scope_revision"
    ]


# ---------------------------------------------------------------------------
# dependency_graph_revision delivery row (dependency-class, 2 migrated cases)
# ---------------------------------------------------------------------------


def test_run_episode_dependency_graph_revision_delivery_row_presented(
    tmp_path: Path, monkeypatch,
) -> None:
    """A dependency_graph_revision-tagged authority delivery row is presented.

    The dependency-class authorities (e.g. ``mab-dependency-unblock-107bc4fe3f``
    ``mab-late-constraint-9636e9ce85``) stamp ``dependency_graph_revision`` on a
    result-bearing authority; ``run_episode`` must deliver it to the participant
    under the tagged event id and never consume it through the live seam.
    """
    events = [
        {"id": "evt.dep.revision", "stimulus_type": "dependency_graph_revision",
         "result": "result_authority", "workstream_id": "authority"},
    ]
    case = _write_case(
        tmp_path, case_id="dep-delivery", events=events,
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
    transcript.append({
        "type": "child_completed", "child_id": "ca-authority",
        "completion_id": "authority-1",
        "result_kind": "result_authority", "payload": {"result": "final"},
    })
    transcript.append({"type": "episode_ended", "final_answer": "done",
                       "local_status": "completed", "declared_task_success": True})
    _patch_live_adapter(monkeypatch, transcript, sink)
    config = _live_episode_config(tmp_path, case, "delivery-dep")
    asyncio.run(runner_module.run_episode(ROOT, config))

    deliveries = [m for m in sink if m.get("type") == "result_delivered"]
    assert deliveries, "authority delivery was never presented to the adapter"
    assert deliveries[-1]["completion_id"] == "authority-1"

    facts = [
        r for r in _trace_rows(tmp_path)
        if r.get("type") == "result_delivery_evaluator_fact"
    ]
    assert facts, "delivery evaluator fact never reached the trace"
    assert facts[0]["completion_id"] == "authority-1"
    assert facts[0]["result_kind"] == "result_authority"
    assert facts[0]["benchmark_event_id"] == "evt.dep.revision"

    assert not [
        r for r in _trace_rows(tmp_path)
        if r.get("type") == "dependency_graph_revision"
    ]


# ---------------------------------------------------------------------------
# task_scope_revision live row (result-less mechanism fired at child boundary)
# ---------------------------------------------------------------------------


def test_run_episode_live_scope_revision_audits_and_is_never_delivered(
    tmp_path: Path, monkeypatch,
) -> None:
    """A result-less task_scope_revision row is a live mechanism, not a delivery.

    It fires once at the first child boundary, recording a kernel-private
    revision audit; because it carries no result role it is never presented to
    the participant as a ``result_delivered``.
    """
    case = _write_case(tmp_path, case_id="scope-live", events=[
        {"id": "evt.scope.live", "stimulus_type": "task_scope_revision",
         "revision_id": "r-live", "new_scope": {"phase": "frozen"},
         "participant_visible_fields": {"notice": "scope changed to frozen"}},
    ], bindings={"authority": {"result_kind": "result_authority"}})
    sink: list[dict] = []
    _patch_live_adapter(monkeypatch, _adapter_events(("c1", "authority")), sink)
    config = _live_episode_config(tmp_path, case, "live-scope")
    asyncio.run(runner_module.run_episode(ROOT, config))

    facts = [r for r in _trace_rows(tmp_path) if r.get("type") == "task_scope_revision"]
    assert facts, "task_scope_revision audit never reached the trace"
    assert facts[0]["revision_id"] == "r-live"
    assert facts[0]["changed"] is True
    assert facts[0]["visibility"] == "kernel_private"
    # The live mechanism row is never delivered to the participant.
    assert not [m for m in sink if m.get("type") == "result_delivered"]


def test_controller_keeps_live_and_delivery_scope_rows_apart() -> None:
    """A schedule may declare the revision in both forms; the seam separates them.

    The delivery row (carrying a ``result`` role) must be ignored by the live
    seam -- it is governed by ``_drain`` -- while the live row (no result)
    fires exactly once at the first child boundary.
    """
    case = {
        "scenarios": {"linear": {"events": []}, "async": {"events": [
            # Delivery form: tagged authority delivery (the migrated rows).
            {"id": "delivery", "stimulus_type": "task_scope_revision",
             "result": "result_authority", "workstream_id": "authority"},
            # Live form: a separate mechanism row with no result role.
            {"id": "live", "stimulus_type": "task_scope_revision",
             "revision_id": "r-live", "new_scope": {"phase": "frozen"},
             "participant_visible_fields": {"notice": "frozen"}},
        ]}},
    }
    controller = DeliveryController("async", case)
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    deliveries = controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c1",
    })
    assert deliveries == []
    assert len(controller.revision_audits) == 1
    assert controller.revision_audits[0]["type"] == "task_scope_revision"
    assert controller.revision_audits[0]["revision_id"] == "r-live"
    # Idempotent: no live row fires a second time on another child boundary.
    controller.on_child_started({"type": "child_started", "child_id": "c2"})
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c2",
    }) == []
    assert len(controller.revision_audits) == 1


# ---------------------------------------------------------------------------
# migrated schedule shape validates
# ---------------------------------------------------------------------------


def test_migrated_scope_schedule_shape_validates() -> None:
    """The schedule authoring used by the 38 migrated cases passes the taxonomy.

    Mirrors the SWE/TBN form (authority tagged task_scope_revision bound after
    ``after_artifacts``) and the MAB dependency-class form (authority tagged
    dependency_graph_revision bound after ``after_results``).
    """
    common = {
        "allowed_results": {"result_01", "result_02", "result_03", "result_04"},
        "workstream_ids": {"requirement_worker_01", "requirement_worker_02",
                           "requirement_worker_03", "requirement_worker_04"},
        "known_artifacts": {"provisional_checkpoint", "preserved_source_facts",
                            "final_state"},
        "known_milestones": {"consume_async_evidence", "reverify_and_close"},
    }
    swe_scope = [
        {"id": "evt.swe.scope.workstream", "result": "result_01"},
        {"id": "evt.swe.scope", "result": "result_02",
         "stimulus_type": "task_scope_revision", "workstream_id": "requirement_worker_02",
         "invalidates_artifacts": ["final_state"],
         "reopens_milestones": ["consume_async_evidence", "reverify_and_close"],
         "trigger": "after_artifacts_committed",
         "after_artifacts": ["provisional_checkpoint", "preserved_source_facts"]},
    ]
    mab_dep = [
        {"id": "evt.mab.dep.upstream_01", "result": "result_01"},
        {"id": "evt.mab.dep.upstream_02", "result": "result_02"},
        {"id": "evt.mab.dep.upstream_03", "result": "result_03"},
        {"id": "evt.mab.dep", "result": "result_04",
         "stimulus_type": "dependency_graph_revision", "workstream_id": "requirement_worker_02",
         "invalidates_artifacts": ["final_state"],
         "reopens_milestones": ["consume_async_evidence", "reverify_and_close"],
         "trigger": "after_results_delivered",
         "after_results": ["result_01", "result_02", "result_03"]},
    ]
    assert validate_scenario_events(swe_scope, execution_mode="async", **common) == []
    assert validate_scenario_events(mab_dep, execution_mode="async", **common) == []

    # A revision event that neither invalidates nor reopens observable state is
    # rejected by the taxonomy (both migrated forms must carry effects).
    broken = [dict(event) for event in swe_scope]
    broken[-1] = {
        k: v for k, v in broken[-1].items()
        if k not in {"invalidates_artifacts", "reopens_milestones"}
    }
    errors = validate_scenario_events(broken, execution_mode="async", **common)
    assert any("revision event must invalidate or reopen observable state" in error
               for error in errors)
