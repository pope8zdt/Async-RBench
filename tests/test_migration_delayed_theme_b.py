"""Task 10 migration conformance for delayed_authoritative_result (B half).

The lane migrates the second half (by lexicographic case id) of the 90
registered cases whose ``primary_event_theme`` is
``delayed_authoritative_result``: 27 osw-family and 18 swe-family cases.  The
migration author is exactly the frozen lane-0a delayed contract:

* every semantic check is tagged with exactly one ``score_domain``
  (``base_task`` | ``async_replanning``); the ``event_integration`` (receipt /
  probes) and ``closure`` checks are ``async_replanning`` and bind the focal
  authority scenario event id, while ``provenance`` / ``source_semantics`` /
  ``changed_behavior`` / ``preserved_behavior`` checks are ``base_task`` (no
  ``event_id``).  ``relevance_tier`` is retained.
* the control-flow registry's ``event_contracts`` observation contract reads
  ``required_changes=[final_state]`` (the delayed authority invalidates the
  provisional ``final_state``), ``required_preservation=[preserved_source_facts]``
  (the source baseline stays byte-stable), ``forbidden_changes=[provisional_checkpoint]``
  (the pre-authority record is never rewritten), ``closure_checks`` resolving to
  the case's real ``.closure`` semantic id, the self-authored disposition token
  ``adopt_delayed_authority_and_replan_downstream``, and ``event_status=scored``.
* the private design ledger mirrors the evaluator registry, and the top-level
  ``event_contracts`` in ``private_case.yaml`` mirror the registry contract.

The runtime half drives the DeliveryController and ``run_episode`` and asserts
the theme semantics the migration data describes: the delayed authority is never
presented before the provisional downstream result that gates it, and when it is
released it invalidates ``final_state`` and reopens the closure milestones
(``consume_async_evidence`` / ``reverify_and_close``) -- the "adopt the authority
and replan downstream" contract -- while the provisional checkpoint is preserved.
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
EXPECTED_DISPOSITION = "adopt_delayed_authority_and_replan_downstream"
# A delayed authority invalidates exactly the provisional final_state and reopens
# the two closure milestones (uniform across all 45 migrated authorities).
AUTHORITY_INVALIDATES = ["final_state"]
AUTHORITY_REOPENS = ["consume_async_evidence", "reverify_and_close"]
# async_replanning checks are exactly the event_integration + closure families.
ASYNC_CATEGORIES = frozenset({"event_integration", "closure"})
ASYNC_CAPABILITIES = frozenset({
    "async_result_integration", "async_consistency_closure",
})

# The 45 second-half delayed cases migrated by this lane (lexicographic split of
# the 90 registered delayed cases at len // 2).
EXPECTED_MIGRATED_DIRS = frozenset({
    "osw-cross-app-artifact-95969c461f",
    "osw-cross-app-artifact-98b42677e4",
    "osw-cross-app-artifact-9923123786",
    "osw-cross-app-artifact-be9a3df3ef",
    "osw-cross-app-artifact-c449a6c0e0",
    "osw-dependency-unblock-0008d814cb",
    "osw-dependency-unblock-0ec654e205",
    "osw-dependency-unblock-166790a6f2",
    "osw-dependency-unblock-1a3f65b5b8",
    "osw-dependency-unblock-201b3549f3",
    "osw-dependency-unblock-22ed3b1d66",
    "osw-dependency-unblock-2d1b650a2e",
    "osw-dependency-unblock-3686cb057d",
    "osw-dependency-unblock-3e78382c85",
    "osw-dependency-unblock-4bfe607faa",
    "osw-dependency-unblock-5c3a1789cf",
    "osw-dependency-unblock-72d6a6fe27",
    "osw-dependency-unblock-75855f9fc5",
    "osw-dependency-unblock-af63091471",
    "osw-dependency-unblock-af91d8977d",
    "osw-dependency-unblock-ba52abb8a2",
    "osw-dependency-unblock-e804a9f769",
    "osw-late-test-evidence-5b3f5ffce5",
    "osw-late-test-evidence-67c3504794",
    "osw-late-test-evidence-befa686e5c",
    "osw-late-test-evidence-f5d523fc9a",
    "osw-state-reconciliation-b384f1d300",
    "swe-dependency-unblock-00437a10dc",
    "swe-dependency-unblock-08463030bf",
    "swe-dependency-unblock-3deaf34cf4",
    "swe-dependency-unblock-3fa1a02dd5",
    "swe-dependency-unblock-4a74272d52",
    "swe-dependency-unblock-4b1feb8a91",
    "swe-dependency-unblock-50946f0528",
    "swe-dependency-unblock-53e5b92cf8",
    "swe-dependency-unblock-5c30d720ef",
    "swe-dependency-unblock-82115ba350",
    "swe-dependency-unblock-f27fc59f3c",
    "swe-late-constraint-3a01a4fcef",
    "swe-late-constraint-acaa77b306",
    "swe-late-test-evidence-739f820ffd",
    "swe-late-test-evidence-94f318cd83",
    "swe-late-test-evidence-9f62f0f149",
    "swe-late-test-evidence-b844373562",
    "swe-late-test-evidence-d83b778f04",
})


def _delayed_theme_dirs() -> list[Path]:
    """Every registered delayed case in this checkout (both halves are present)."""
    from async_rbench.spec import discover_cases
    return sorted(
        case.case_dir
        for case in discover_cases(ROOT)
        if (case.raw.get("classification") or {}).get("primary_event_theme")
        == "delayed_authoritative_result"
    )


def _second_half_dirs() -> list[Path]:
    dirs = _delayed_theme_dirs()
    split = len(dirs) // 2
    return sorted(dirs[split:])


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Migration data guards over the 45 migrated second-half delayed cases
# ---------------------------------------------------------------------------


def test_lane_targets_the_second_half_delayed_cases() -> None:
    """The lane owns the lexicographic second half of the 90 delayed cases."""
    all_dirs = _delayed_theme_dirs()
    assert len(all_dirs) == 90, len(all_dirs)
    second_half = {case_dir.name for case_dir in _second_half_dirs()}
    assert second_half == EXPECTED_MIGRATED_DIRS
    # Deterministic, non-overlapping split: the halves partition the theme set.
    first_half = {case_dir.name for case_dir in all_dirs[: len(all_dirs) // 2]}
    assert not (first_half & EXPECTED_MIGRATED_DIRS)


def test_every_delayed_case_check_has_exactly_one_scoring_domain() -> None:
    for case_dir in _second_half_dirs():
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        contracts = control.get("event_contracts") or []
        assert len(contracts) == 1, case_dir.name
        focal_event_id = str(contracts[0]["event_id"])
        closure_async = []
        for check in semantic["checks"]:
            check_id = str(check["id"])
            domain = check.get("score_domain")
            assert domain in SCORE_DOMAINS, (case_dir.name, check_id, domain)
            # relevance_tier is deliberately retained in the migrated file.
            assert "relevance_tier" in check, (case_dir.name, check_id)
            category = str(check.get("category") or "")
            capability = str(check.get("capability_target") or "")
            if domain == "async_replanning":
                # Event-integrating async checks bind the focal authority id.
                assert category in ASYNC_CATEGORIES, (case_dir.name, check_id)
                assert capability in ASYNC_CAPABILITIES, (case_dir.name, check_id)
                assert str(check.get("event_id") or "") == focal_event_id, (
                    case_dir.name, check_id, check.get("event_id"), focal_event_id,
                )
                if check_id.endswith(".closure"):
                    closure_async.append(check_id)
            else:
                assert category not in ASYNC_CATEGORIES, (case_dir.name, check_id)
                assert capability not in ASYNC_CAPABILITIES, (case_dir.name, check_id)
                assert check.get("event_id") is None, (
                    case_dir.name, check_id, "base_task carried event_id",
                )
        assert len(closure_async) == 1, (case_dir.name, closure_async)


def test_every_delayed_case_event_contract_carries_observation_contract() -> None:
    for case_dir in _second_half_dirs():
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        contracts = control.get("event_contracts") or []
        assert len(contracts) == 1, case_dir.name
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        semantic_ids = {str(c["id"]) for c in semantic["checks"]}
        contract = contracts[0]
        missing = [field for field in OBSERVATION_FIELDS if field not in contract]
        assert not missing, (case_dir.name, contract.get("event_id"), missing)
        assert contract["event_theme"] == "delayed_authoritative_result", case_dir.name
        # Downstream must be revised to the authority; the source baseline is
        # preserved; the pre-authority provisional checkpoint is never rewritten.
        assert contract["required_changes"] == ["final_state"], case_dir.name
        assert contract["required_preservation"] == ["preserved_source_facts"], case_dir.name
        assert contract["forbidden_changes"] == ["provisional_checkpoint"], case_dir.name
        closure_ids = contract["closure_checks"] or []
        assert closure_ids, (case_dir.name, contract.get("event_id"))
        for closure_id in closure_ids:
            assert closure_id in semantic_ids, (case_dir.name, closure_id)
        assert contract["expected_disposition"] == EXPECTED_DISPOSITION, case_dir.name
        assert contract["event_status"] == "scored", case_dir.name
        # The private design ledger mirrors the evaluator registry full-file, and
        # private_case.yaml's top-level event_contracts mirror the registry too.
        ledger = _load(case_dir / "private" / "dynamic_point_plan.json")
        assert ledger == control, case_dir.name
        private = yaml.safe_load(
            (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        assert private["event_contracts"] == contracts, case_dir.name


def test_every_delayed_authority_declares_the_authority_effects() -> None:
    """The focal event exists in the schedule, is an authority delivery, and its
    delayed arrival invalidates final_state and reopens the closure milestones."""
    for case_dir in _second_half_dirs():
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        focal = str(control["event_contracts"][0]["event_id"])
        private = yaml.safe_load(
            (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        events = (private.get("scenarios") or {}).get("async", {}).get("events", [])
        authority = next((e for e in events if e.get("id") == focal), None)
        assert authority is not None, (case_dir.name, focal)
        assert authority.get("result") is not None, (case_dir.name, focal)
        assert list(authority.get("invalidates_artifacts") or []) == AUTHORITY_INVALIDATES, (
            case_dir.name, focal,
        )
        assert list(authority.get("reopens_milestones") or []) == AUTHORITY_REOPENS, (
            case_dir.name, focal,
        )
        # No stale machinery: a delayed authority does not demote later arrivals.
        assert private.get("stale_predicate") is None, case_dir.name


# ---------------------------------------------------------------------------
# Minimal runnable case fixture (mirrors the migrated delayed authoring shape)
# ---------------------------------------------------------------------------


def _write_case(
    tmp_path: Path,
    *,
    case_id: str,
    events: list[dict],
    workstream_ids: list[str] | None = None,
    bindings: dict | None = None,
) -> Path:
    workstream_ids = workstream_ids or ["provisional"]
    bindings = dict(bindings or {})
    case = tmp_path / case_id
    (case / "private").mkdir(parents=True)
    (case / "task" / "tests").mkdir(parents=True)
    (case / "task" / "assets").mkdir(parents=True)
    (case / "public_case.yaml").write_text(yaml.safe_dump({
        "format_version": 2, "case_id": case_id,
        "title": "Delayed authoritative result",
        "task_instruction_path": "task/task.yaml",
        "workstreams": [{
            "id": stream_id, "task": "recover", "targets": [],
            "expected_output": "out", "priority": "normal",
        } for stream_id in workstream_ids],
        "artifacts": [],
    }), encoding="utf-8")
    (case / "private/private_case.yaml").write_text(yaml.safe_dump({
        "case_id": case_id,
        "workstream_bindings": bindings,
        "authoritative_result_kind": "result_authority",
        "result_contract": {
            "allowed_result_kinds": ["result_provisional", "result_authority"],
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


def _delayed_events() -> list[dict]:
    """Two result-bearing deliveries: a provisional result, then the delayed
    authority (gated on the provisional, invalidating final_state)."""
    return [
        {"id": "evt.delayed.provisional", "result": "result_provisional",
         "invalidates_artifacts": [], "reopens_milestones": []},
        {"id": "evt.delayed.authority", "result": "result_authority",
         "trigger": "after_results_delivered",
         "after_results": ["result_provisional"],
         "invalidates_artifacts": list(AUTHORITY_INVALIDATES),
         "reopens_milestones": list(AUTHORITY_REOPENS)},
    ]


def _base_case(events: list[dict]) -> dict:
    return {
        "authoritative_result_kind": "result_authority",
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
# DeliveryController semantics (provisional first, delayed authority second)
# ---------------------------------------------------------------------------


def test_delayed_authority_is_held_until_the_provisional_result_is_presented() -> None:
    """A delayed authority whose window waits on the provisional downstream result
    is not presented early; it is released only after the provisional arrival,
    in arrival order -- and when released it carries the replanning contract."""
    events = [
        {"id": "evt.delayed.provisional", "result": "result_provisional"},
        {"id": "evt.delayed.authority", "result": "result_authority",
         "trigger": "after_results_delivered",
         "after_results": ["result_provisional"],
         "invalidates_artifacts": list(AUTHORITY_INVALIDATES),
         "reopens_milestones": list(AUTHORITY_REOPENS)},
    ]
    controller = DeliveryController("async", _base_case(events))
    controller.spawned = {"c1": {}, "c2": {}}
    # The authority completion races ahead of the provisional; its delivery
    # window is not yet open, so nothing is presented to the participant yet.
    early = controller.on_complete(_completion("c1", "auth-1", "result_authority", {"rev": "A1"}))
    assert early == []
    # The provisional arrives; both are now released, provisional first.
    released = controller.on_complete(
        _completion("c2", "prov-1", "result_provisional", {"rev": "P1"})
    )
    assert [m.get("completion_id") for m in released] == ["prov-1", "auth-1"]
    authority = released[1]
    assert authority["benchmark_event_id"] == "evt.delayed.authority"
    # Adopt the delayed authority and replan downstream: final_state is
    # invalidated and the closure milestones reopen; the pre-authority
    # provisional checkpoint is never invalidated (preserved as the frozen
    # record of provisional work), and there is no stale demotion.
    assert authority["invalidates_artifacts"] == AUTHORITY_INVALIDATES
    assert authority["reopens_milestones"] == AUTHORITY_REOPENS
    assert authority["stale"] is False
    assert authority["evaluator_stale"] is False


def test_delayed_provisional_and_authority_are_two_distinct_occurrences() -> None:
    """The delayed authority is an additional delivery occurrence -- the adopt +
    replan step is never merged back into the provisional result."""
    controller = DeliveryController(
        "async", _base_case(_delayed_events()),
    )
    controller.spawned = {"c1": {}, "c2": {}}
    first = controller.on_complete(
        _completion("c1", "prov-1", "result_provisional", {"rev": "P1"})
    )
    second = controller.on_complete(
        _completion("c2", "auth-1", "result_authority", {"rev": "A1"})
    )
    all_messages = first + second
    assert [m.get("completion_id") for m in all_messages] == ["prov-1", "auth-1"]
    occurrences = [m["delivery_occurrence_id"] for m in all_messages]
    assert len(occurrences) == len(set(occurrences)) == 2
    assert all(m.get("controlled_order") for m in all_messages)


# ---------------------------------------------------------------------------
# run_episode end-to-end: delayed authority arrives and replans downstream
# ---------------------------------------------------------------------------


def test_run_episode_delayed_authority_delivered_then_replans_downstream(
    tmp_path: Path, monkeypatch,
) -> None:
    """End-to-end: the provisional result is presented first; the delayed
    authority that follows is presented under its tagged event id and its
    kernel fact records that final_state is invalidated and the closure
    milestones are reopened -- while the provisional checkpoint is preserved."""
    events = _delayed_events()
    case = _write_case(
        tmp_path, case_id="delayed-b", events=events,
        workstream_ids=["provisional", "authority"],
        bindings={
            "provisional": {"result_kind": "result_provisional"},
            "authority": {"result_kind": "result_authority"},
        },
    )
    sink: list[dict] = []
    transcript = _adapter_events(
        ("cp-provisional", "provisional"), ("ca-authority", "authority"),
    )
    # Provisional downstream work completes first, then the authority arrives.
    transcript.append({
        "type": "child_completed", "child_id": "cp-provisional",
        "completion_id": "provisional-1",
        "result_kind": "result_provisional", "payload": {"checkpoint": "P1"},
    })
    transcript.append({
        "type": "child_completed", "child_id": "ca-authority",
        "completion_id": "authority-1",
        "result_kind": "result_authority", "payload": {"revised": "final"},
    })
    transcript.append({"type": "episode_ended", "final_answer": "done",
                       "local_status": "completed", "declared_task_success": True})
    _patch_live_adapter(monkeypatch, transcript, sink)
    config = _live_episode_config(tmp_path, case, "delayed-b")
    asyncio.run(runner_module.run_episode(ROOT, config))

    # The participant sees both public deliveries, provisional before authority.
    deliveries = [m for m in sink if m.get("type") == "result_delivered"]
    assert len(deliveries) == 2, "expected provisional + delayed authority deliveries"
    assert [m["completion_id"] for m in deliveries] == ["provisional-1", "authority-1"]
    assert deliveries[0]["payload"] == {"checkpoint": "P1"}
    assert deliveries[1]["payload"] == {"revised": "final"}
    # Public shape: no evaluator control truth leaks to the participant.
    for message in deliveries:
        assert "result_kind" not in message
        assert "benchmark_event_id" not in message
        assert "invalidates_artifacts" not in message

    facts = [
        r for r in _trace_rows(tmp_path)
        if r.get("type") == "result_delivery_evaluator_fact"
    ]
    assert len(facts) == 2, "both deliveries must carry kernel evaluator facts"
    provisional, authority = facts[0], facts[1]
    assert provisional["completion_id"] == "provisional-1"
    assert provisional["result_kind"] == "result_provisional"
    assert provisional["benchmark_event_id"] == "evt.delayed.provisional"
    assert provisional["invalidates_artifacts"] == []
    assert provisional["reopens_milestones"] == []
    assert authority["completion_id"] == "authority-1"
    assert authority["result_kind"] == "result_authority"
    assert authority["benchmark_event_id"] == "evt.delayed.authority"
    # Replanning contract: final_state invalidated, closure milestones reopened,
    # and the provisional checkpoint is preserved (never invalidated).
    assert authority["invalidates_artifacts"] == AUTHORITY_INVALIDATES
    assert authority["reopens_milestones"] == AUTHORITY_REOPENS
    assert authority["delivery_occurrence_id"] != provisional["delivery_occurrence_id"]
    assert authority["replayed"] is False


# ---------------------------------------------------------------------------
# migrated schedule authoring shapes validate
# ---------------------------------------------------------------------------


def test_migrated_delayed_schedule_shapes_validate() -> None:
    """The two in-tree delayed authority forms pass the scenario taxonomy.

    The osw-family (27 cases) chains the authority on ``after_results_delivered``;
    the swe-family (18 cases) gates it on ``after_artifacts_committed`` (some rows
    additionally carry a theme/revision tag that resolves to the same pure
    delivery semantics).  Both end in an authority that invalidates ``final_state``
    and reopens the closure milestones.
    """
    common = {
        "allowed_results": {"result_01", "result_02", "result_03", "result_04"},
        "workstream_ids": {"requirement_worker_01", "requirement_worker_02",
                           "requirement_worker_03", "requirement_worker_04",
                           "upstream_worker_01", "upstream_worker_02",
                           "upstream_worker_03", "upstream_worker_04"},
        "known_artifacts": {"provisional_checkpoint", "preserved_source_facts",
                            "final_state"},
        "known_milestones": {"consume_async_evidence", "reverify_and_close"},
    }
    osw_chain = [
        {"id": "evt.osw.delayed.workstream_01", "result": "result_01"},
        {"id": "evt.osw.delayed.workstream_02", "result": "result_02",
         "trigger": "after_results_delivered", "after_results": ["result_01"]},
        {"id": "evt.osw.delayed", "result": "result_03",
         "trigger": "after_results_delivered",
         "after_results": ["result_01", "result_02"],
         "invalidates_artifacts": list(AUTHORITY_INVALIDATES),
         "reopens_milestones": list(AUTHORITY_REOPENS)},
    ]
    swe_chain = [
        {"id": "evt.swe.delayed.workstream_01", "result": "result_01"},
        {"id": "evt.swe.delayed", "result": "result_02",
         "stimulus_type": "delayed_authoritative_result",
         "trigger": "after_artifacts_committed",
         "after_artifacts": ["provisional_checkpoint", "preserved_source_facts"],
         "invalidates_artifacts": list(AUTHORITY_INVALIDATES),
         "reopens_milestones": list(AUTHORITY_REOPENS)},
    ]
    assert validate_scenario_events(osw_chain, execution_mode="async", **common) == []
    assert validate_scenario_events(swe_chain, execution_mode="async", **common) == []
