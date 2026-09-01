from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases/rebuild-batch-001/batch-manifest.json"
CASE_IDS = [
    str(item["case_id"])
    for item in json.loads(BATCH.read_text(encoding="utf-8"))["cases"]
]


def _spawn_initial_wave(controller: DeliveryController, case: dict) -> dict[str, str]:
    children: dict[str, str] = {}
    for index, workstream in enumerate(case["initial_wave"], 1):
        workstream_id = str(workstream["workstream_id"])
        child_id = f"child-{index}"
        children[workstream_id] = child_id
        controller.on_spawn({
            "type": "child_spawned",
            "child_id": child_id,
            "parent_id": "main",
            "work_units": [workstream_id],
        })
    return children


def _completion(
    child_id: str, completion_id: str, result_kind: str,
) -> dict:
    return {
        "type": "child_completed",
        "child_id": child_id,
        "completion_id": completion_id,
        "result_kind": result_kind,
        "payload": {"summary": result_kind, "evidence": {"revision": "reference"}},
    }


def _run_reference(case_id: str, *, authority_valid: bool) -> tuple[dict, dict]:
    case = load_case(ROOT / "cases" / case_id / "public_case.yaml").raw
    controller = DeliveryController("async", case)
    children = _spawn_initial_wave(controller, case)
    result_to_workstream = {
        str(item["result_kind"]): str(item["id"])
        for item in case["delegation_workstreams"]
    }
    control = json.loads(
        (ROOT / "cases" / case_id / "task/tests/control_flow_checks.json").read_text(
            encoding="utf-8"
        )
    )
    event_id = str(control["event_contracts"][0]["event_id"])
    event = next(
        item for item in case["scenarios"]["async"]["events"]
        if str(item["id"]) == event_id
    )
    authority_kind = str(case["authoritative_result_kind"])
    authority_workstream = result_to_workstream[authority_kind]
    authority_completion = _completion(
        children[authority_workstream], "authority-completion", authority_kind,
    )
    validation = SimpleNamespace(
        valid=authority_valid,
        reason_codes=() if authority_valid else ("reference_negative_fixture",),
    )
    deliveries = controller.on_complete(authority_completion, validation)
    assert deliveries == []

    trigger = str(event.get("trigger") or "immediate")
    if trigger == "after_artifacts_committed":
        for artifact_id in event["after_artifacts"]:
            deliveries.extend(controller.on_observation({
                "type": "artifact_committed", "artifact_id": artifact_id,
            }))
    elif trigger == "after_results_delivered":
        for index, result_kind in enumerate(event["after_results"], 1):
            workstream_id = result_to_workstream[str(result_kind)]
            deliveries.extend(controller.on_complete(
                _completion(
                    children[workstream_id], f"prerequisite-{index}", str(result_kind),
                ),
                SimpleNamespace(valid=True, reason_codes=()),
            ))
    else:
        raise AssertionError(f"unexpected first-10 trigger {trigger!r}")

    causal = [item for item in deliveries if item.get("benchmark_event_id") == event_id]
    assert len(causal) == 1
    return case, causal[0]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_positive_reference_delivers_one_authority_bound_causal_event(case_id: str) -> None:
    case, delivery = _run_reference(case_id, authority_valid=True)
    assert delivery["type"] == "result_delivered"
    assert delivery["result_kind"] == case["authoritative_result_kind"]
    assert delivery["invalidates_artifacts"]
    assert delivery["reopens_milestones"]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_negative_reference_rejects_without_losing_causal_event_identity(case_id: str) -> None:
    case, rejection = _run_reference(case_id, authority_valid=False)
    assert rejection["type"] == "result_rejected"
    assert rejection["result_kind"] == case["authoritative_result_kind"]
    assert rejection["reason_codes"] == ["reference_negative_fixture"]
