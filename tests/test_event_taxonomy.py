from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from async_rbench.evaluation.event_coverage import build_event_coverage
from async_rbench.evaluation.event_taxonomy import (
    EVENT_THEME_IDS,
    validate_event_taxonomy,
    validate_event_theme_fixtures,
)
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.spec import CaseSpec, discover_cases, load_case, validate_case


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
        "type": "completion_replay",
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
                    "id": "replay", "type": "completion_replay",
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
