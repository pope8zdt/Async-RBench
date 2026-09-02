"""Task 10 migration conformance for the late_or_out_of_order_superseded_result theme.

The 21 registered case dirs of this theme (20 v7 evaluator registries plus the
legacy v4 ``secure-release``) author the six observation fields on their event
contract:

* ``required_changes`` / ``required_preservation`` / ``forbidden_changes`` /
  ``closure_checks`` / ``expected_disposition`` / ``event_status`` (the MAB
  artifact vocabulary: only the authority advances ``final_state``, the
  preserved source facts stay identical, and the superseded older
  ``provisional_checkpoint`` is never rewritten);
* every semantic check carries exactly one ``score_domain`` (``async_replanning``
  bound to the authority event id for async capabilities, ``base_task``
  otherwise) and retains ``relevance_tier``;
* v7 dirs mirror the full event_contracts across control / dynamic-point-plan /
  private top-level; the legacy v4 dir adds control-only ``event_contracts``
  bound to its authoritative scenario event (the committed git-conflict legacy
  migration shape: no private/ledger mirrors, ``forbidden_changes`` empty).

The runtime half drives the DeliveryController and a full ``run_episode`` with a
scripted adapter.  Both use the theme's real evaluator vocabulary
(``superseded_result_kind = result_01`` / ``authoritative_result_kind =
result_02``, revision-mismatch predicate over ``accepted_current_revision`` vs
``delivered_offer.revision``) to prove the disposition the contracts describe:
the authority is presented only after its superseded result is released (FIFO,
one occurrence per delivery), and a superseded old occurrence that arrives after
the authority is current is flagged evaluator-stale -- never re-presented as a
fresh current result, and never rolling the accepted authority back.
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

LATE_THEME = "late_or_out_of_order_superseded_result"
V7_DISPOSITION = "adopt_authority_and_reject_late_superseded_result"
V4_DISPOSITION = "adopt_clean_authority_reject_pre_rewrite_deployment"

SCORE_DOMAINS = frozenset({"base_task", "async_replanning"})
OBSERVATION_FIELDS = (
    "required_changes",
    "required_preservation",
    "forbidden_changes",
    "closure_checks",
    "expected_disposition",
    "event_status",
)

EXPECTED_LATE_DIRS = frozenset({
    "mab-dependency-unblock-1c96d4414d",
    "mab-late-constraint-0e3747a21b",
    "mab-late-constraint-19947db02f",
    "mab-late-constraint-1e1fa7c00b",
    "mab-late-constraint-23f25a7748",
    "mab-late-constraint-4412b3e2d6",
    "mab-late-constraint-49a364ba43",
    "mab-late-constraint-6f495ee7e8",
    "mab-late-constraint-88206c382b",
    "mab-late-constraint-89a5f5d134",
    "mab-late-constraint-99180ff520",
    "mab-late-constraint-9bcba02feb",
    "mab-late-constraint-aa71803693",
    "mab-late-constraint-c4cd816269",
    "mab-late-constraint-c7d591d986",
    "mab-late-constraint-c88a633e8f",
    "mab-late-constraint-db9b3a6953",
    "mab-late-constraint-eb55acdb83",
    "mab-late-constraint-efb76e596e",
    "mab-late-constraint-f395d7243c",
    "secure-release",
})


def _late_cases() -> list[Path]:
    """The registered case dirs whose primary_event_theme is late supersede."""
    cases = []
    for case in discover_cases(ROOT):
        private = yaml.safe_load(
            (case.case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        theme = ((private.get("classification") or {}).get("primary_event_theme") or "")
        if theme == LATE_THEME:
            cases.append(case.case_dir)
    return sorted(cases)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Migration data guards (the 21 registered late-supersede cases)
# ---------------------------------------------------------------------------


def test_lane_targets_the_21_registered_late_cases() -> None:
    target_dirs = {case_dir.name for case_dir in _late_cases()}
    assert target_dirs == EXPECTED_LATE_DIRS


def test_every_late_case_check_has_exactly_one_scoring_domain() -> None:
    """Each migrated semantic check carries exactly one resolvable score_domain."""
    for case_dir in _late_cases():
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
            if domain == "async_replanning":
                event_id = str(check.get("event_id") or "")
                assert event_id in contract_event_ids, (
                    case_dir.name, check_id, event_id, contract_event_ids,
                )
            elif check.get("event_id") is not None:
                raise AssertionError((case_dir.name, check_id, "base_task carried event_id"))


def test_every_late_case_contract_carries_observation_fields_and_resolves() -> None:
    """Six observation fields present; closure refs resolve; mirrors agree.

    v7 dirs must mirror the full contract across control / dynamic-point-plan /
    private top-level.  The legacy v4 ``secure-release`` carries control-only
    ``event_contracts`` (no private/ledger mirror exists for the legacy format,
    mirroring the committed git-conflict-and-cleanup-closure migration) and is
    the one case where ``forbidden_changes`` may be empty.
    """
    for case_dir in _late_cases():
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        version = str(control.get("version"))
        semantic_ids = {str(check["id"]) for check in semantic["checks"]}
        assert semantic_ids

        contracts = control.get("event_contracts") or []
        assert contracts, case_dir.name
        for contract in contracts:
            missing = [field for field in OBSERVATION_FIELDS if field not in contract]
            assert not missing, (case_dir.name, contract.get("event_id"), missing)
            assert isinstance(contract.get("required_changes"), list)
            assert isinstance(contract.get("required_preservation"), list)
            assert isinstance(contract.get("forbidden_changes"), list)
            assert contract.get("required_changes"), (case_dir.name, "required_changes")
            assert contract.get("required_preservation"), (case_dir.name, "required_preservation")
            # Every closure reference must resolve to a real semantic check id
            # (review-fix precedent 9a0a811: a dash-form directory reference
            # silently pins the closure component at 0.0).  Real ids carry the
            # underscore form with a trailing suffix that may be `.closure`,
            # `.closure.receipt` or `.sem.NN.closure`; the resolution (subset)
            # check is the load-bearing guard, never the literal suffix.
            refs = {str(item) for item in contract.get("closure_checks")}
            assert refs <= semantic_ids, (case_dir.name, refs - semantic_ids)
            assert refs and not any(
                str(item) == f"{case_dir.name}.closure" for item in refs
            ), case_dir.name
            assert str(contract.get("expected_disposition") or "").strip()
            assert contract.get("event_status") == "scored"
        if version == "7":
            # Three-mirror equality and the theme's single non-empty closure ref.
            ledger = _load(case_dir / "private" / "dynamic_point_plan.json")
            private = _load(case_dir / "private" / "private_case.yaml")
            assert ledger == control, case_dir.name
            assert private.get("event_contracts") == contracts, case_dir.name
            assert len(contracts) == 1, case_dir.name
            for contract in contracts:
                assert contract["required_changes"] == ["final_state"], case_dir.name
                assert contract["required_preservation"] == ["preserved_source_facts"], case_dir.name
                assert contract["forbidden_changes"] == ["provisional_checkpoint"], case_dir.name
                assert contract["expected_disposition"] == V7_DISPOSITION, case_dir.name
        else:
            assert version == "4", (case_dir.name, version)
            assert case_dir.name == "secure-release", case_dir.name
            for contract in contracts:
                assert contract.get("event_theme") == LATE_THEME, case_dir.name
                assert contract["expected_disposition"] == V4_DISPOSITION, case_dir.name
                # Legacy format mirrors the git-conflict v4 template: forbidden
                # is declared empty because there is no provisional checkpoint
                # artifact in that legacy file vocabulary.
                assert contract["forbidden_changes"] == [], case_dir.name


def test_real_late_case_closure_component_scores_full_value() -> None:
    """The real underscore closure id yields a full closure score, not 0.0.

    ``_closure_score`` joins semantic results by exact check id.  The migrated
    cases reference ``{underscore_case}.closure`` (the real semantic check);
    when that check passes the closure component must be 1.0 and add its quarter
    to the process score.  A directory-name (dash-form) reference resolves to
    nothing and returns 0.0 -- the regression the straggler lane's first pass
    shipped and the reviewer rejected.
    """
    case_dir = next(
        case_dir for case_dir in _late_cases()
        if str(_load(case_dir / "task" / "tests" / "control_flow_checks.json").get("version")) == "7"
    )
    control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
    semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
    contracts = control.get("event_contracts") or []
    assert len(contracts) == 1
    contract = contracts[0]
    refs = {str(item) for item in contract["closure_checks"]}
    semantic_ids = {str(check["id"]) for check in semantic["checks"]}
    assert refs <= semantic_ids, (case_dir.name, refs - semantic_ids)

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


# ---------------------------------------------------------------------------
# Runtime theme semantics (multi-result arrival at the DeliveryController)
# ---------------------------------------------------------------------------
#
# The migrated MAB cases author two result roles with the theme's vocabulary:
#   superseded_result_kind = result_01   (older provisional)
#   authoritative_result_kind = result_02  (the authority, released only after
#   result_01 has been delivered; invalidates final_state, reopens the
#   consume_async_evidence / reverify_and_close milestones)
# and a revision-mismatch predicate that compares the accepted current revision
# (authority evidence) against the delivered_offer revision of a superseded
# occurrence.


def _late_spec() -> dict:
    return {
        "authoritative_result_kind": "result_02",
        "superseded_result_kind": "result_01",
        "stale_predicate": {
            "type": "revision_mismatch",
            "authoritative_fields": ["accepted_current_revision"],
            "superseded_fields": ["delivered_offer.revision"],
        },
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "evt.mab.late.provisional", "result": "result_01"},
                {"id": "evt.mab.late.authority", "result": "result_02",
                 "trigger": "after_results_delivered", "after_results": ["result_01"],
                 "invalidates_artifacts": ["final_state"],
                 "reopens_milestones": ["consume_async_evidence", "reverify_and_close"]},
            ]},
        },
    }


def _completion(child_id: str, completion_id: str, result_kind: str, evidence: dict) -> dict:
    return {
        "type": "child_completed",
        "child_id": child_id,
        "completion_id": completion_id,
        "result_kind": result_kind,
        "payload": {"evidence": evidence},
    }


def test_authority_is_held_until_superseded_result_is_presented() -> None:
    """The authority is never presented ahead of its superseded result.

    An authority completion that arrives first is held; releasing the superseded
    provisional result is what opens the window, after which both are presented
    in that arrival order (FIFO), one delivery occurrence per result.
    """
    controller = DeliveryController("async", _late_spec())
    controller.spawned = {"c1": {}, "c2": {}}
    early = controller.on_complete(
        _completion("c1", "auth-1", "result_02", {"accepted_current_revision": "R2"})
    )
    assert early == [], "authority must not precede its superseded result"
    released = controller.on_complete(
        _completion("c2", "prov-1", "result_01", {"delivered_offer.revision": "R1"})
    )
    assert [message.get("result_kind") for message in released] == ["result_01", "result_02"]
    assert [message.get("stale") for message in released] == [False, False]
    assert controller.delivery_order == ["prov-1", "auth-1"]


def test_each_late_result_is_one_occurrence_in_the_presentation_window() -> None:
    """Two results are presented as two distinct deliveries/occurrences."""
    controller = DeliveryController("async", _late_spec())
    controller.spawned = {"c1": {}, "c2": {}}
    first = controller.on_complete(
        _completion("c2", "prov-1", "result_01", {"delivered_offer.revision": "R1"})
    )
    second = controller.on_complete(
        _completion("c1", "auth-1", "result_02", {"accepted_current_revision": "R2"})
    )
    all_messages = first + second
    assert [m.get("result_kind") for m in all_messages] == ["result_01", "result_02"]
    occurrences = [m["delivery_occurrence_id"] for m in all_messages]
    assert len(occurrences) == len(set(occurrences)) == 2
    assert all(m.get("stale_visibility") == "explicit" for m in all_messages)
    assert all(m.get("evaluator_stale") is False for m in all_messages)


def test_late_superseded_old_occurrence_after_authority_is_stale_no_rollback() -> None:
    """A superseded old occurrence after the authority is current is stale.

    Once the authority has been delivered, a second, late superseded result_01
    (an older ``delivered_offer.revision``) is evaluator-stale: it cannot be
    re-presented as the current truth.  The authority is not rolled back -- it
    stays the only accepted current result and is never re-delivered.
    """
    controller = DeliveryController("async", _late_spec())
    controller.spawned = {"c1": {}, "c2": {}}
    authority = controller.on_complete(
        _completion("c1", "auth-1", "result_02", {"accepted_current_revision": "R2"})
    )
    # The normal flow presents the superseded provisional first, releasing the
    # held authority in the same drain.
    assert authority == []
    provisional = controller.on_complete(
        _completion("c2", "prov-1", "result_01", {"delivered_offer.revision": "R1"})
    )
    assert [m.get("result_kind") for m in provisional] == ["result_01", "result_02"]
    assert all(m.get("evaluator_stale") is False for m in provisional)

    # A late, out-of-order superseded old occurrence arrives afterwards.
    late = controller.on_complete(
        _completion("c2", "prov-late", "result_01", {"delivered_offer.revision": "R1"})
    )
    assert late
    message = late[0]
    assert message["result_kind"] == "result_01"
    assert message["stale"] is True
    assert message["stale_visibility"] == "explicit"
    assert message["evaluator_stale"] is True
    assert message["evaluator_stale_measurable"] is True
    assert message["evaluator_stale_reason"] == (
        "delivered_offer.revision=R1 != accepted_current_revision=R2"
    )
    # No rollback: the authority was presented once, stays before the late
    # occurrence in the delivery order, and no fresh result_02 reappears.
    authority_deliveries = [
        completion_id
        for completion_id in controller.delivery_order
        if controller.completions[completion_id].get("result_kind") == "result_02"
    ]
    assert authority_deliveries == ["auth-1"]
    assert controller.delivery_order == ["prov-1", "auth-1", "prov-late"]


# ---------------------------------------------------------------------------
# run_episode e2e with a scripted adapter (late-supersede disposition)
# ---------------------------------------------------------------------------


def _write_late_case(tmp_path: Path, *, case_id: str) -> Path:
    case = tmp_path / case_id
    (case / "private").mkdir(parents=True)
    (case / "task" / "tests").mkdir(parents=True)
    (case / "task" / "assets").mkdir(parents=True)
    public = {
        "format_version": 2,
        "case_id": case_id,
        "title": "Declared late superseded result",
        "task_instruction_path": "task/task.yaml",
        "workstreams": [
            {"id": stream_id, "task": "recover", "targets": [],
             "expected_output": "out", "priority": "normal"}
            for stream_id in ("requirement_worker_01", "requirement_worker_02")
        ],
        "artifacts": [],
    }
    (case / "public_case.yaml").write_text(yaml.safe_dump(public), encoding="utf-8")
    private = {
        "case_id": case_id,
        "workstream_bindings": {
            "requirement_worker_01": {"result_kind": "result_01"},
            "requirement_worker_02": {"result_kind": "result_02"},
        },
        "authoritative_result_kind": "result_02",
        "superseded_result_kind": "result_01",
        "result_contract": {"allowed_result_kinds": ["result_01", "result_02"]},
        "stale_predicate": {
            "type": "revision_mismatch",
            "authoritative_fields": ["accepted_current_revision"],
            "superseded_fields": ["delivered_offer.revision"],
        },
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "evt.late.provisional", "result": "result_01"},
                {"id": "evt.late.authority", "result": "result_02",
                 "trigger": "after_results_delivered", "after_results": ["result_01"],
                 "invalidates_artifacts": ["final_state"],
                 "reopens_milestones": ["consume_async_evidence", "reverify_and_close"]},
            ]},
        },
    }
    (case / "private/private_case.yaml").write_text(
        yaml.safe_dump(private), encoding="utf-8")
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


def _base_adapter_events(*streams: tuple[str, str]) -> list[dict]:
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


def test_run_episode_late_authority_presented_stale_old_occurrence_no_rollback(
    tmp_path: Path, monkeypatch,
) -> None:
    """End-to-end: the authority closes the provisional window, not vice versa.

    The scripted participant first delivers its superseded provisional
    (result_01) -- presented normally because no authority exists yet -- then the
    authority (result_02) is presented with its reopen/invalidate markers.  A
    second, late result_01 occurrence (an older offer revision) is then
    delivered by the participant: the gateway must present it only once, flagged
    evaluator-stale, and must not roll the authority back or re-present it.
    """
    case = _write_late_case(tmp_path, case_id="late-supersede")
    sink: list[dict] = []
    transcript = _base_adapter_events(
        ("c1", "requirement_worker_01"), ("c2", "requirement_worker_02"),
    )
    # 1. The superseded provisional result arrives and is presented.
    transcript.append({
        "type": "child_completed", "child_id": "c1", "completion_id": "prov-1",
        "result_kind": "result_01",
        "payload": {"evidence": {"delivered_offer.revision": "offer-R1"}},
    })
    # 2. The authority result arrives (held until result_01 was delivered).
    transcript.append({
        "type": "child_completed", "child_id": "c2", "completion_id": "auth-1",
        "result_kind": "result_02",
        "payload": {"evidence": {"accepted_current_revision": "offer-R2"}},
    })
    # 3. A late, out-of-order superseded old occurrence shows up afterwards.
    transcript.append({
        "type": "child_spawned", "child_id": "c3", "parent_id": "main",
        "work_units": ["requirement_worker_01"],
    })
    transcript.append({"type": "child_started", "child_id": "c3"})
    transcript.append({
        "type": "child_completed", "child_id": "c3", "completion_id": "prov-late",
        "result_kind": "result_01",
        "payload": {"evidence": {"delivered_offer.revision": "offer-R1"}},
    })
    transcript.append({"type": "episode_ended", "final_answer": "done",
                       "local_status": "completed", "declared_task_success": True})
    _patch_live_adapter(monkeypatch, transcript, sink)
    config = _live_episode_config(tmp_path, case, "late-e2e")
    asyncio.run(runner_module.run_episode(ROOT, config))

    # The gateway presents each result once, in participant order, under public
    # shape (no result_kind / benchmark_event_id / stale leak into the adapter
    # stream; the double projection to the adapter drops the workstream binding,
    # which is recorded separately on the gateway trace rows).
    deliveries = [m for m in sink if m.get("type") == "result_delivered"]
    assert [m["completion_id"] for m in deliveries] == ["prov-1", "auth-1", "prov-late"]
    assert deliveries[0]["payload"]["evidence"] == {"delivered_offer.revision": "offer-R1"}
    assert deliveries[1]["payload"]["evidence"] == {"accepted_current_revision": "offer-R2"}
    assert deliveries[2]["payload"]["evidence"] == {"delivered_offer.revision": "offer-R1"}
    for message in deliveries:
        assert "result_kind" not in message
        assert "benchmark_event_id" not in message
        assert "evaluator_stale" not in message
    gateway_deliveries = [
        r for r in _trace_rows(tmp_path)
        if r.get("type") == "result_delivered" and r.get("completion_id")
    ]
    assert [r["workstream_id"] for r in gateway_deliveries] == [
        "requirement_worker_01", "requirement_worker_02", "requirement_worker_01",
    ]

    # The kernel separately records the evaluator truth: the authority (and only
    # the authority) reopens the closure milestones; the late superseded old
    # occurrence is the sole stale delivery and never displaces the authority.
    facts = [r for r in _trace_rows(tmp_path) if r.get("type") == "result_delivery_evaluator_fact"]
    assert [f["completion_id"] for f in facts] == ["prov-1", "auth-1", "prov-late"]
    assert [f["result_kind"] for f in facts] == ["result_01", "result_02", "result_01"]
    assert [f["stale"] for f in facts] == [False, False, True]
    assert facts[1]["invalidates_artifacts"] == ["final_state"]
    assert facts[1]["reopens_milestones"] == ["consume_async_evidence", "reverify_and_close"]
    assert facts[2]["stale_reason"] == (
        "delivered_offer.revision=offer-R1 != accepted_current_revision=offer-R2"
    )
    occurrences = [f["delivery_occurrence_id"] for f in facts]
    assert occurrences and len(occurrences) == len(set(occurrences)) == 3
    # No replay, no rollback, no spontaneous re-presentation of the authority.
    assert all(f["replayed"] is False for f in facts)
    assert [f["result_kind"] for f in facts].count("result_02") == 1
    assert not [
        r for r in _trace_rows(tmp_path) if r.get("type") == "result_rejection_evaluator_fact"
    ]
