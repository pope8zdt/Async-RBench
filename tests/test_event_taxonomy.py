from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from async_rbench.evaluation.event_coverage import build_event_coverage
from async_rbench.evaluation.event_taxonomy import (
    EVENT_THEME_IDS,
    validate_event_taxonomy,
    validate_event_theme_fixtures,
    validate_scenario_events,
)
from async_rbench.evaluation.protocol import (
    GATEWAY_STIMULUS_EVENT_REQUIREMENTS,
    validate_gateway_event,
)
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.spec import CaseSpec, discover_cases, load_case, validate_case


def _well_formed_stimulus(event_type: str) -> dict:
    """A minimal protocol-valid gateway stimulus audit fact of the given type."""
    if event_type == "task_scope_revision":
        return {
            "type": event_type, "revision_id": "r1",
            "before_digest": "a" * 64, "after_digest": "b" * 64,
            "changed": True, "participant_visible": {},
            "expected_response_preserved": True,
        }
    if event_type == "dependency_graph_revision":
        return {
            "type": event_type, "revision_id": "dg1",
            "before_digest": "a" * 64, "after_digest": "b" * 64,
            "changed": True,
            "affected_edges": {"db": {
                "before_digest": "c" * 64, "after_digest": "d" * 64,
            }},
            "participant_visible": {},
            "expected_response_preserved": True,
        }
    if event_type == "resource_pressure":
        return {
            "type": event_type, "straggler_child_id": "c1", "applied": True,
            "active_children": ["c1", "c2"], "active_count": 2,
            "resource": "concurrency_slot", "concurrency_limit": 2,
            "pool_remaining": 1,
        }
    if event_type == "deadline_update":
        return {
            "type": event_type, "before_deadline": None, "after_deadline": 100,
            "applied_before_response_window": True,
            "response_window_active": False, "reason": "sla",
        }
    if event_type == "child_terminal_outcome":
        return {
            "type": event_type, "child_id": "c1", "completion_id": "p1",
            "outcome": "timeout", "designed": True, "was_in_flight": True,
            "detail": "designed timeout",
        }
    raise AssertionError(f"unknown stimulus event type {event_type!r}")


ROOT = Path(__file__).resolve().parents[1]


def test_taxonomy_defines_eight_valid_event_themes_and_fixtures() -> None:
    assert len(EVENT_THEME_IDS) == 8
    assert validate_event_taxonomy(ROOT / "event_taxonomy.json") == []
    assert validate_event_theme_fixtures() == []


def test_current_cases_have_private_event_classification() -> None:
    for case in discover_cases(ROOT):
        assert not validate_case(case), case.case_id
        public = yaml.safe_load(case.path.read_text(encoding="utf-8"))
        private = yaml.safe_load(
            (case.case_dir / "private/private_case.yaml").read_text(encoding="utf-8")
        )
        assert "classification" not in public
        assert private["classification"]["primary_event_theme"] in EVENT_THEME_IDS


def test_validate_requires_numeric_deadline_wall_on_deadline_update() -> None:
    """A live deadline_update row must carry a numeric deadline_wall.

    The seam reads it through float(), so validate rejects a missing, empty, or
    non-numeric declaration up front (deadline_update rows also require a valid
    workstream_id, as they are workstream-scoped stimulus kinds).
    """
    kwargs = {
        "execution_mode": "async",
        "allowed_results": {"authority", "provisional"},
        "workstream_ids": {"provisional_stream", "authority_stream"},
        "known_artifacts": {"final"},
        "known_milestones": {"integrate"},
    }
    valid = validate_scenario_events(
        [{"id": "d1", "stimulus_type": "deadline_update", "deadline_wall": 3600.0,
          "workstream_id": "provisional_stream"}],
        **kwargs,
    )
    assert valid == []
    missing = validate_scenario_events(
        [{"id": "d2", "stimulus_type": "deadline_update",
          "workstream_id": "provisional_stream"}],
        **kwargs,
    )
    assert any("must declare a numeric deadline_wall" in error for error in missing)
    non_numeric = validate_scenario_events(
        [{"id": "d3", "stimulus_type": "deadline_update",
          "deadline_wall": "2026-09-03T00:00:00Z", "workstream_id": "provisional_stream"}],
        **kwargs,
    )
    assert any("deadline_wall must be numeric" in error for error in non_numeric)


def test_current_coverage_counts_events_and_capabilities_independently() -> None:
    cases = discover_cases(ROOT)
    report = build_event_coverage(cases)
    assert report["valid"] is True
    assert sum(report["primary_event_theme_counts"].values()) == len(cases)
    assert sum(report["capability_counts"].values()) > len(cases)
    assert report["missing_primary_event_themes"] == []


def test_completion_replay_is_not_a_duplicate_result_schedule() -> None:
    source = load_case(ROOT / "cases/data-recovery-service/public_case.yaml")
    raw = deepcopy(source.raw)
    original = raw["scenarios"]["async"]["events"][0]
    raw["scenarios"]["async"]["events"].append({
        "id": "replay-checkpoint",
        "stimulus_type": "completion_replay",
        "replay_of_result": original["result"],
        "trigger": "after_consumed",
    })
    assert validate_case(CaseSpec(path=source.path, raw=raw)) == []


def test_new_dependency_event_does_not_require_a_fake_superseded_result() -> None:
    source = load_case(ROOT / "cases/data-recovery-service/public_case.yaml")
    raw = deepcopy(source.raw)
    raw["superseded_result_kind"] = None
    assert "superseded_result_kind is not allowed" not in validate_case(
        CaseSpec(path=source.path, raw=raw)
    )


def test_replay_preserves_completion_identity_and_fires_once() -> None:
    case = {
        "authoritative_result_kind": "authority",
        "superseded_result_kind": "provisional",
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "authority", "result": "authority"},
                {
                    "id": "replay", "stimulus_type": "completion_replay",
                    "replay_of_result": "authority", "trigger": "after_consumed",
                },
            ]},
        },
    }
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    original = controller.on_complete({
        "child_id": "c1", "completion_id": "p1", "result_kind": "authority",
        "payload": {"revision": "v2"},
    })[0]
    replay = controller.on_consumed({"completion_id": "p1"})
    assert len(replay) == 1
    assert replay[0]["completion_id"] == original["completion_id"]
    assert replay[0]["payload_sha256"] == original["payload_sha256"]
    assert replay[0]["replayed"] is True
    assert controller.on_consumed({"completion_id": "p1"}) == []


def test_specialized_gateway_stimulus_audits_validate_cleanly() -> None:
    """Every gateway-owned stimulus audit fact is protocol-valid when well formed."""
    assert GATEWAY_STIMULUS_EVENT_REQUIREMENTS
    for event_type in GATEWAY_STIMULUS_EVENT_REQUIREMENTS:
        fact = _well_formed_stimulus(event_type)
        assert validate_gateway_event(fact) == [], event_type


def test_resource_pressure_audit_rejects_straggler_outside_active_children() -> None:
    """A pressure activation must name a straggler that is demonstrably active."""
    fact = _well_formed_stimulus("resource_pressure")
    fact["active_children"] = ["c2"]
    errors = validate_gateway_event(fact)
    assert any("straggler_child_id" in error for error in errors)


def test_dependency_graph_revision_audit_rejects_non_sha_digests() -> None:
    """Affected-edge digests must be real SHA-256 hex strings."""
    fact = _well_formed_stimulus("dependency_graph_revision")
    fact["affected_edges"]["db"]["after_digest"] = "not-a-digest"
    errors = validate_gateway_event(fact)
    assert any("after_digest" in error for error in errors)


def test_specialized_stimulus_types_form_the_five_gateway_audit_families() -> None:
    """The gateway audit registry names every evaluator-owned stimulus producer."""
    assert set(GATEWAY_STIMULUS_EVENT_REQUIREMENTS) == {
        "task_scope_revision", "dependency_graph_revision",
        "resource_pressure", "deadline_update",
        "child_terminal_outcome",
    }
