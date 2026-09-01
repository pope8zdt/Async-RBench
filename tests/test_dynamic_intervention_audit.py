import json
from pathlib import Path

import yaml

from async_rbench.dynamic_pilot import _causal_interruption_evidence


def _write_case(tmp_path: Path, *, with_contract: bool) -> Path:
    case = tmp_path / "case"
    (case / "private").mkdir(parents=True)
    event = {
        "id": "authority",
        "result": "result_03",
        "trigger": "after_artifacts_committed",
        "after_artifacts": ["runtime_state"],
        "invalidates_artifacts": ["runtime_state"],
    }
    if with_contract:
        event["intervention"] = {
            "required_changed_artifacts": ["runtime_state"],
        }
    private = {
        "classification": {"async_scenario_class": "live_eventful"},
        "authoritative_result_kind": "result_03",
        "scenarios": {"async": {"events": [event]}},
    }
    (case / "private/private_case.yaml").write_text(
        yaml.safe_dump(private), encoding="utf-8",
    )
    return case


def _write_trace(tmp_path: Path, *, intervention: bool) -> Path:
    rows = [{
        "type": "artifact_committed", "seq": 1,
        "artifact_id": "runtime_state", "observed_digest": "a" * 64,
    }]
    if intervention:
        rows.append({
            "type": "intervention_applied", "seq": 2,
            "benchmark_event_id": "authority", "passed": True,
            "required_changed_artifacts": ["runtime_state"],
            "changed_artifacts": ["runtime_state"],
        })
    rows.append({
        "type": "result_delivery_evaluator_fact", "seq": 3,
        "result_kind": "result_03", "benchmark_event_id": "authority",
        "delivery_fallback_reason": None,
    })
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8",
    )
    return trace


def test_live_case_without_intervention_proof_is_benchmark_invalid(tmp_path: Path) -> None:
    evidence = _causal_interruption_evidence(
        _write_case(tmp_path, with_contract=False),
        _write_trace(tmp_path, intervention=False),
    )
    assert evidence["passed"] is False
    assert "lacks an evaluator-owned intervention contract" in evidence["reason"]


def test_missing_model_recommit_does_not_invalidate_real_intervention(tmp_path: Path) -> None:
    evidence = _causal_interruption_evidence(
        _write_case(tmp_path, with_contract=True),
        _write_trace(tmp_path, intervention=True),
    )
    assert evidence["passed"] is True
    assert evidence["model_missing_post_authority_recommits"] == ["runtime_state"]
    assert evidence["live_intervention_evidence"]["passed"] is True
