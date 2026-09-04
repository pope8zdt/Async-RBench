from __future__ import annotations

import json
from argparse import Namespace
from types import SimpleNamespace

from async_rbench import eval_cli


def test_offline_rescore_keeps_delivery_infrastructure_failure_unscored(
    tmp_path, monkeypatch, capsys,
) -> None:
    case_dir = tmp_path / "case"
    tests_dir = case_dir / "task" / "tests"
    tests_dir.mkdir(parents=True)
    contract_path = case_dir / "public_case.yaml"
    contract_path.write_text("case_id: fixture\n", encoding="utf-8")
    (tests_dir / "semantic_checks.json").write_text(
        json.dumps({"checks": [{"id": "sem"}]}), encoding="utf-8",
    )
    (tests_dir / "control_flow_checks.json").write_text(
        json.dumps({
            "checks": [],
            "event_contracts": [{
                "event_id": "evt.authority", "expected_disposition": "revise",
                "required_changes": ["final"],
            }],
        }),
        encoding="utf-8",
    )
    case_spec = {
        "initial_wave": [
            {"workstream_id": "provisional"},
            {"workstream_id": "authority"},
        ],
        "delegation_workstreams": [
            {"id": "provisional", "result_kind": "provisional_result"},
            {"id": "authority", "result_kind": "authority_result"},
        ],
        "authoritative_result_kind": "authority_result",
        "superseded_result_kind": "provisional_result",
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
        "artifacts": [{"id": "final"}],
    }
    monkeypatch.setattr(
        eval_cli, "resolve_case_instance",
        lambda *_: SimpleNamespace(contract_path=contract_path, case_dir=case_dir),
    )
    monkeypatch.setattr(eval_cli, "load_case", lambda *_: SimpleNamespace(raw=case_spec))

    events = [
        {
            "type": "child_spawned", "seq": 1, "child_id": "p",
            "parent_id": "main", "work_units": ["provisional"],
            "initial_wave": True,
        },
        {
            "type": "child_spawned", "seq": 2, "child_id": "a",
            "parent_id": "main", "work_units": ["authority"],
            "initial_wave": True,
        },
        {"type": "child_started", "seq": 3, "child_id": "p"},
        {"type": "child_started", "seq": 4, "child_id": "a"},
        {
            "type": "verifier_result", "seq": 5,
            "semantic_check_results": [{"id": "sem", "passed": True}],
            "test_point_pass_rate": 1.0,
        },
        {
            "type": "infrastructure_failure", "seq": 6,
            "component": "delivery_intervention", "detail": "mutation failed",
        },
    ]
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8",
    )
    output_path = tmp_path / "offline-score.json"

    eval_cli.cmd_score(Namespace(
        legacy=False, trace=str(trace_path), case="fixture", instance="seed-1",
        execution_mode="async", output=str(output_path),
    ))
    capsys.readouterr()
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert report["async_drs"] is None
    assert report["score_status"] == "unscored"
    assert report["score_status_reason"] == "dynamic_scenario_qualification_failed"
