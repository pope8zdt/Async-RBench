"""Migration guards for the ``conflicting_valid_results`` swimlane (Task 10).

The lane migrates the six cases whose ``primary_event_theme`` is
``conflicting_valid_results`` to the new scoring contract:

* every semantic check is tagged with exactly one ``score_domain``
  (``base_task`` | ``async_replanning``); an ``async_replanning`` check binds the
  theme's authoritative scenario event id, while ``relevance_tier`` is retained.
* the control-flow registry's ``event_contracts`` observation contract expresses
  the theme resolution (only the authority is presentable; the superseded
  conflicting provisional cannot displace it) via ``required_changes`` /
  ``required_preservation`` / ``forbidden_changes`` / ``closure_checks`` /
  ``expected_disposition`` / ``event_status``.

The runtime half drives the DeliveryController with two valid results arriving
and asserts the theme semantics the migration data describes: the authority is
held until the conflicting provisional window is presented (FIFO, one occurrence
per window), and a provisional that arrives after the authority is evaluator-stale
and cannot be re-presented as the current truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.spec import discover_cases

ROOT = Path(__file__).resolve().parents[1]
CONFLICTING_RESULT_KINDS = ("provisional", "authority")
SCORE_DOMAINS = frozenset({"base_task", "async_replanning"})
OBSERVATION_FIELDS = (
    "required_changes",
    "required_preservation",
    "forbidden_changes",
    "closure_checks",
    "expected_disposition",
    "event_status",
)

EXPECTED_CONFLICTING_DIRS = frozenset({
    "git-conflict-and-cleanup-closure",
    "mab-conflicting-specialist-results-5f19377089",
    "mab-conflicting-specialist-results-8f1d6fd6fd",
    "mab-conflicting-specialist-results-ce3ff5b928",
    "mab-conflicting-specialist-results-cf7b930f57",
    "scheduler-selective-replan",
})


def _conflicting_cases() -> list[Path]:
    cases = []
    for case in discover_cases(ROOT):
        private = yaml.safe_load(
            (case.case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        theme = ((private.get("classification") or {}).get("primary_event_theme") or "")
        if theme == "conflicting_valid_results":
            cases.append(case.case_dir)
    return sorted(cases)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Migration data guards
# ---------------------------------------------------------------------------


def test_lane_targets_the_six_registered_conflicting_cases() -> None:
    target_dirs = {case_dir.name for case_dir in _conflicting_cases()}
    assert target_dirs == EXPECTED_CONFLICTING_DIRS


def test_every_conflicting_case_check_has_exactly_one_scoring_domain() -> None:
    for case_dir in _conflicting_cases():
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


def test_every_conflicting_case_event_contract_carries_observation_fields() -> None:
    for case_dir in _conflicting_cases():
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        contracts = control.get("event_contracts") or []
        assert contracts, case_dir.name
        for contract in contracts:
            missing = [field for field in OBSERVATION_FIELDS if field not in contract]
            assert not missing, (case_dir.name, contract.get("event_id"), missing)
            assert isinstance(contract.get("required_changes"), list)
            assert isinstance(contract.get("required_preservation"), list)
            assert isinstance(contract.get("forbidden_changes"), list)
            assert contract.get("closure_checks"), (case_dir.name, contract.get("event_id"))
            assert str(contract.get("expected_disposition") or "").strip()
            assert contract.get("event_status") == "scored"
        # The private design ledger (where present) mirrors the evaluator registry.
        ledger_path = case_dir / "private" / "dynamic_point_plan.json"
        if ledger_path.exists():
            assert _load(ledger_path) == control, case_dir.name


# ---------------------------------------------------------------------------
# Runtime theme semantics (multi-result arrival at the DeliveryController)
# ---------------------------------------------------------------------------


def _base_case(events: list[dict], stale_predicate: dict | None) -> dict:
    return {
        "authoritative_result_kind": "authority",
        "superseded_result_kind": "provisional",
        "stale_predicate": stale_predicate,
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


def test_authority_is_held_until_prerequisite_provisional_is_delivered() -> None:
    """A conflicting authority whose delivery waits on the provisional result is
    not presented early; it is released only after the provisional arrival,
    keeping the two valid results in arrival order (a FIFO presentation window)."""
    case = _base_case(
        events=[
            {"id": "prov", "result": "provisional"},
            {"id": "auth", "result": "authority",
             "trigger": "after_results_delivered", "after_results": ["provisional"]},
        ],
        stale_predicate=None,
    )
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    # The authority completion arrives first; its window is not yet open because
    # the conflicting provisional has not been presented.  Nothing is delivered.
    early = controller.on_complete(_completion("c1", "auth-1", "authority", {"rev": "R2"}))
    assert early == []
    # The provisional arrives: both results are now released in arrival order.
    released = controller.on_complete(_completion("c2", "prov-1", "provisional", {"rev": "R1"}))
    assert [message.get("result_kind") for message in released] == list(CONFLICTING_RESULT_KINDS)
    assert [message.get("stale") for message in released] == [False, False]
    assert controller.delivery_order == ["prov-1", "auth-1"]


def test_each_result_is_one_occurrence_in_the_presentation_window() -> None:
    """Two valid results are presented as two distinct deliveries/occurrences, so
    the FIFO window never merges the conflicting provisional into the authority."""
    case = _base_case(
        events=[
            {"id": "prov", "result": "provisional"},
            {"id": "auth", "result": "authority"},
        ],
        stale_predicate=None,
    )
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    first = controller.on_complete(_completion("c1", "prov-1", "provisional", {"rev": "R1"}))
    second = controller.on_complete(_completion("c2", "auth-1", "authority", {"rev": "R2"}))
    all_messages = first + second
    assert [m.get("result_kind") for m in all_messages] == list(CONFLICTING_RESULT_KINDS)
    occurrences = [m["delivery_occurrence_id"] for m in all_messages]
    assert len(occurrences) == len(set(occurrences)) == 2
    assert all(m.get("stale_visibility") == "explicit" for m in all_messages)


def test_late_superseded_conflict_is_stale_after_authority_presented() -> None:
    """Once the authority has been delivered, a conflicting provisional arriving
    later (with a superseded revision) is evaluator-stale: it can no longer be
    presented as the current truth (only the authority is visible)."""
    case = _base_case(
        events=[
            {"id": "auth", "result": "authority"},
            {"id": "prov", "result": "provisional"},
        ],
        stale_predicate={
            "type": "revision_mismatch",
            "authoritative_fields": ["secret_hash"],
            "superseded_fields": ["scan_revision"],
        },
    )
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    authority = controller.on_complete(
        _completion("c1", "auth-1", "authority", {"evidence": {"secret_hash": "H1"}})
    )
    assert authority and authority[0]["evaluator_stale"] is False
    late = controller.on_complete(
        _completion("c2", "prov-late", "provisional", {"evidence": {"scan_revision": "H9"}})
    )
    assert late
    message = late[0]
    assert message["result_kind"] == "provisional"
    assert message["stale"] is True
    assert message["evaluator_stale"] is True
    assert message["evaluator_stale_measurable"] is True
    assert message["evaluator_stale_reason"] == "scan_revision=H9 != secret_hash=H1"
    # The authority remains the only current (non-stale) delivered result.
    assert controller.delivery_order == ["auth-1", "prov-late"]
