"""Migration guards for the ``delayed_authoritative_result`` swimlane, half A (Task 10).

The lane migrates the first half (45 cases, sorted by case_id) of the cases whose
``primary_event_theme`` is ``delayed_authoritative_result`` to the new scoring
contract:

* every semantic check is tagged with exactly one ``score_domain``
  (``base_task`` | ``async_replanning``); an ``async_replanning`` check binds the
  authoritative scenario event id while ``relevance_tier`` is retained.
* the control-flow registry's ``event_contracts`` observation contract expresses
  the delayed-theme resolution (the late authoritative result supersedes the
  earlier provisional; the provisional must not stand as the final state) via
  ``required_changes`` / ``required_preservation`` / ``forbidden_changes`` /
  ``closure_checks`` / ``expected_disposition`` / ``event_status``.

``distributed-model-runtime`` is the lane's legacy case (format_version 2, no
``event_policy.json``): it receives a single authoritative observation contract
in the v4 control registry (no fabricated v7 gateway fields) and score_domain
tags on its frozen 24 v3 semantic checks.

The runtime half drives the DeliveryController with a provisional and a delayed
authoritative result and asserts the theme semantics the migrated data describes:
a late authority is presented only behind the provisional occurrence in the FIFO
presentation window (each result one occurrence), and a superseded provisional
that arrives after the authority is evaluator-stale and can no longer be
presented as the current truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from async_rbench.evaluation.scheduler import DeliveryController
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
# Frozen delayed-theme boundary: 90 registered delayed cases, this lane owns the
# first 45 by case_id. (registry order: distributed-model-runtime, mab-*, osw-*)
FROZEN_DELAYED_THEME_COUNT = 90

EXPECTED_LANE_A_DIRS = frozenset({
    "distributed-model-runtime",
    "mab-conflicting-specialist-results-0298f78d18",
    "mab-conflicting-specialist-results-0c3537087a",
    "mab-conflicting-specialist-results-8f6f0d514a",
    "mab-conflicting-specialist-results-9ec14bb2f1",
    "mab-conflicting-specialist-results-e5660e25aa",
    "mab-conflicting-specialist-results-eda6fc53e2",
    "mab-cross-app-artifact-2763fffe05",
    "mab-dependency-unblock-0394988930",
    "mab-dependency-unblock-18d7c09304",
    "mab-dependency-unblock-284a3e6eea",
    "mab-dependency-unblock-309c3b9f50",
    "mab-dependency-unblock-472d364155",
    "mab-dependency-unblock-5585821bdf",
    "mab-dependency-unblock-5b3239e261",
    "mab-dependency-unblock-8aed4c43dd",
    "mab-dependency-unblock-8b943d725b",
    "mab-dependency-unblock-a145b96b70",
    "mab-dependency-unblock-b69316f186",
    "mab-dependency-unblock-b999d1b968",
    "mab-dependency-unblock-ce10d55597",
    "mab-dependency-unblock-ed6082b496",
    "mab-dependency-unblock-fa3ee479d7",
    "mab-late-constraint-311fc423ac",
    "mab-late-constraint-383afddcb0",
    "mab-late-constraint-3a268eae01",
    "mab-late-constraint-7557a58e80",
    "mab-late-constraint-a8830cee22",
    "mab-late-constraint-a9a5dd3ff0",
    "mab-late-constraint-ae2fc903e5",
    "mab-late-constraint-cb2a355435",
    "mab-late-constraint-d8248233eb",
    "mab-late-constraint-e4199e525d",
    "mab-late-constraint-e4a188e60e",
    "mab-late-constraint-e5b9a7c681",
    "mab-late-constraint-f4ef18dd00",
    "mab-late-test-evidence-11ad0b6722",
    "osw-cross-app-artifact-110bdf766b",
    "osw-cross-app-artifact-133984c167",
    "osw-cross-app-artifact-19cdaed8e8",
    "osw-cross-app-artifact-319788e71d",
    "osw-cross-app-artifact-586ab293bc",
    "osw-cross-app-artifact-725ceaa05e",
    "osw-cross-app-artifact-83a415ed0c",
    "osw-cross-app-artifact-87e7d44e48",
})


def _theme_of(case_dir: Path) -> str:
    private = yaml.safe_load(
        (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
    )
    return str((private.get("classification") or {}).get("primary_event_theme") or "")


def _delayed_dirs() -> list[Path]:
    return sorted(
        (case.case_dir for case in discover_cases(ROOT)
         if _theme_of(case.case_dir) == "delayed_authoritative_result"),
        key=lambda path: path.name,
    )


def _lane_a_cases() -> list[Path]:
    return [path for path in _delayed_dirs() if path.name in EXPECTED_LANE_A_DIRS]


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Migration data guards
# ---------------------------------------------------------------------------


def test_lane_a_targets_its_registered_delayed_half() -> None:
    delayed = _delayed_dirs()
    assert len(delayed) == FROZEN_DELAYED_THEME_COUNT
    # The lane owns the first 45 delayed cases by case_id.
    assert [path.name for path in delayed[:45]] == sorted(EXPECTED_LANE_A_DIRS)
    assert len(_lane_a_cases()) == len(EXPECTED_LANE_A_DIRS) == 45


def test_every_lane_a_case_check_has_exactly_one_scoring_domain() -> None:
    for case_dir in _lane_a_cases():
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


def test_every_lane_a_case_event_contract_carries_observation_fields() -> None:
    for case_dir in _lane_a_cases():
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
            assert str(contract.get("event_id") or "").strip()
            assert contract.get("event_theme") == "delayed_authoritative_result"
        # The private design ledger (where present) mirrors the evaluator registry.
        ledger_path = case_dir / "private" / "dynamic_point_plan.json"
        if ledger_path.exists():
            assert _load(ledger_path) == control, case_dir.name


def test_legacy_distributed_model_runtime_carries_single_authoritative_contract() -> None:
    """The lane's legacy case binds one authoritative observation contract to the
    delayed authoritative profile event and keeps its v4/v3 registries intact (no
    event_policy.json, no fabricated v7 gateway fields like arrival_contract)."""
    case_dir = ROOT / "cases" / "distributed-model-runtime"
    assert not (case_dir / "private" / "event_policy.json").exists()
    control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
    assert control["version"] == "4"
    contracts = control.get("event_contracts") or []
    assert len(contracts) == 1
    contract = contracts[0]
    assert contract["event_id"] == "dm_a_profile"
    assert contract["event_theme"] == "delayed_authoritative_result"
    # legacy scope: no v7 gateway fields invented.
    for gateway_field in ("arrival_contract", "authority_source", "required_opportunities"):
        assert gateway_field not in contract, gateway_field
    assert contract["forbidden_changes"] == ["tp_candidate"]
    semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
    assert semantic["version"] == "3"
    assert len(semantic["checks"]) == 24


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


def test_delayed_authority_is_presented_only_behind_the_provisional_occurrence() -> None:
    """The late authoritative result is held in the FIFO presentation window until
    the provisional occurrence has been delivered; only then are both released in
    arrival order, each as one distinct occurrence (never merged)."""
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
    # the provisional has not been presented.  Nothing is delivered.
    early = controller.on_complete(_completion("c1", "auth-1", "authority", {"rev": "R2"}))
    assert early == []
    # The provisional arrives: both results are released in arrival order, the
    # delayed authority behind the provisional occurrence.
    released = controller.on_complete(_completion("c2", "prov-1", "provisional", {"rev": "R1"}))
    assert [message.get("result_kind") for message in released] == ["provisional", "authority"]
    assert [message.get("stale") for message in released] == [False, False]
    assert controller.delivery_order == ["prov-1", "auth-1"]


def test_authority_presentation_is_one_distinct_occurrence_in_the_window() -> None:
    """A provisional and the later authoritative result are presented as two
    distinct deliveries/occurrences; the FIFO window never merges the superseded
    provisional into the authority."""
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
    first = controller.on_complete(_completion("c1", "prov-1", "provisional", {"rev": "R1"}))
    second = controller.on_complete(_completion("c2", "auth-1", "authority", {"rev": "R2"}))
    all_messages = first + second
    assert [m.get("result_kind") for m in all_messages] == ["provisional", "authority"]
    occurrences = [m["delivery_occurrence_id"] for m in all_messages]
    assert len(occurrences) == len(set(occurrences)) == 2
    assert all(m.get("stale_visibility") == "explicit" for m in all_messages)
    assert controller.delivery_order == ["prov-1", "auth-1"]


def test_late_superseded_provisional_is_stale_after_authority_presented() -> None:
    """Once the delayed authoritative result has been presented, a superseded
    provisional arriving later is evaluator-stale: it can no longer be presented
    as the current truth (only the authority is visible)."""
    case = _base_case(
        events=[
            {"id": "prov", "result": "provisional"},
            {"id": "auth", "result": "authority"},
            {"id": "prov-late", "result": "provisional"},
        ],
        stale_predicate={
            "type": "revision_mismatch",
            "authoritative_fields": ["final_value"],
            "superseded_fields": ["tentative_value"],
        },
    )
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}, "c3": {}}
    controller.on_complete(
        _completion("c1", "prov-1", "provisional", {"evidence": {"tentative_value": "V1"}})
    )
    authority = controller.on_complete(
        _completion("c2", "auth-1", "authority", {"evidence": {"final_value": "V2"}})
    )
    assert authority and authority[0]["evaluator_stale"] is False
    late = controller.on_complete(
        _completion("c3", "prov-late", "provisional", {"evidence": {"tentative_value": "V9"}})
    )
    assert late
    message = late[0]
    assert message["result_kind"] == "provisional"
    assert message["stale"] is True
    assert message["evaluator_stale"] is True
    assert message["evaluator_stale_measurable"] is True
    assert message["evaluator_stale_reason"] == "tentative_value=V9 != final_value=V2"
    # The authority remains the only current (non-stale) delivered result.
    assert controller.delivery_order == ["prov-1", "auth-1", "prov-late"]
