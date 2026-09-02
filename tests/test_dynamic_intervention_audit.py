import json
from pathlib import Path

import yaml

from async_rbench.dynamic_pilot import _causal_interruption_evidence
from async_rbench.evaluation.runner import _record_controller_stimulus_audits
from async_rbench.evaluation.scheduler import DeliveryController


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


def test_stimulus_audits_persist_as_kernel_private_evaluator_facts() -> None:
    """Revision/pressure/deadline/terminal audits flush as private, never public."""
    class Recorder:
        def __init__(self) -> None:
            self.rows = []

        def record(self, row, source):
            value = {**row, "source": source}
            self.rows.append(value)
            return value

    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    # Live revision + dependency revision + applied pressure + deadline update.
    controller.apply_task_scope_revision(
        revision_id="r1", new_scope={"seq": 2},
        participant_visible_fields={"notice": "revised"},
        expected_response={"seq": 2},
    )
    controller.apply_dependency_graph_revision(
        revision_id="dg1", new_edges={"db": ("migrate", "backfill")},
        participant_visible_fields={"graph_notice": "edge 1 revised"},
        expected_response={"db": ("migrate", "backfill")},
    )
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    controller.apply_resource_pressure(straggler_child_id="c1", limit=2, pool_remaining=1)
    controller.apply_deadline_update(deadline_wall=1000, reason="sla")
    controller.apply_child_terminal_outcome(
        child_id="c1", completion_id="p1", result_kind="authority",
        payload={"result": "partial"}, outcome="timeout", detail="t", designed=True,
    )

    recorder = Recorder()
    _record_controller_stimulus_audits(controller, recorder)

    types_persisted = {row["type"] for row in recorder.rows}
    assert {"task_scope_revision", "dependency_graph_revision",
            "resource_pressure", "deadline_update",
            "child_terminal_outcome"} <= types_persisted
    assert all(row["source"] == "kernel" for row in recorder.rows)
    # The classifier's private facts never reach the public/participant stream.
    assert all(row.get("visibility") == "kernel_private" for row in recorder.rows)
    # The in-flight proof and before/after boundaries survive the flush.
    pressure = next(row for row in recorder.rows if row["type"] == "resource_pressure")
    assert pressure["applied"] is True
    assert pressure["straggler_in_flight"] is True
    terminal = next(row for row in recorder.rows if row["type"] == "child_terminal_outcome")
    assert terminal["designed"] is True
    assert terminal["was_in_flight"] is True
