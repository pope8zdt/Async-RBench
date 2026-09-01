from __future__ import annotations

import json
from pathlib import Path

from async_rbench.experiment_plan import validate_frozen_release
from async_rbench.evaluation.calibration import audit_score_calibration, _case_split_map


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _frozen_contract() -> dict:
    return {
        "version": "9.1.0",
        "status": "frozen",
        "calibration_diagnostics": {
            "minimum_pilot_models": 5,
            "minimum_model_families": 3,
        },
    }


def _frozen_dataset() -> dict:
    return {"schema_version": "1.0", "status": "post_calibration_locked"}


def _frozen_plan() -> dict:
    return {
        "schema_version": "1.0",
        "calibration_audit": {"gaps": [], "total_gaps": 0},
        "model_panel": [
            {"model_id": f"m{i}", "model_family": f"f{i}", "profile": "configs/x.yaml"}
            for i in range(5)
        ],
    }


def test_freeze_refuses_pre_calibration_repo():
    # The live repo is development/pre_calibration_locked with no calibration
    # audit; the gate must fail closed rather than certify a headline.
    errors = validate_frozen_release(ROOT)
    assert errors, "expected the pre-calibration repo to be refused"
    text = " ".join(errors)
    assert "must be 'frozen'" in text
    assert any("status" in error and "pre_calibration_locked" in error for error in errors)


def test_freeze_accepts_frozen_release(tmp_path: Path):
    _write(tmp_path / "evaluation_contract.json", _frozen_contract())
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    _write(tmp_path / "configs" / "calibration-plan.json", _frozen_plan())
    assert validate_frozen_release(tmp_path) == []


def test_freeze_rejects_dev_version(tmp_path: Path):
    contract = _frozen_contract()
    contract["version"] = "9.1.0-dev"
    _write(tmp_path / "evaluation_contract.json", contract)
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    _write(tmp_path / "configs" / "calibration-plan.json", _frozen_plan())
    assert any("non-dev" in error for error in validate_frozen_release(tmp_path))


def test_freeze_rejects_nonzero_audit_gaps(tmp_path: Path):
    _write(tmp_path / "evaluation_contract.json", _frozen_contract())
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    plan = _frozen_plan()
    plan["calibration_audit"] = {"gaps": ["x"], "total_gaps": 1}
    _write(tmp_path / "configs" / "calibration-plan.json", plan)
    assert any("not zero-gap" in error for error in validate_frozen_release(tmp_path))


def test_freeze_rejects_undersized_panel(tmp_path: Path):
    _write(tmp_path / "evaluation_contract.json", _frozen_contract())
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    plan = _frozen_plan()
    plan["model_panel"] = [{"model_id": "m0", "model_family": "f0", "profile": "x.yaml"}]
    _write(tmp_path / "configs" / "calibration-plan.json", plan)
    assert any("minimum" in error for error in validate_frozen_release(tmp_path))


def test_calibration_audit_rejects_test_split_leak(tmp_path: Path):
    # A calibration audit that admits evidence from a non-calibration family is a
    # leak: development/test instances must never set calibrated weights.
    _write(tmp_path / "evaluation_contract.json", {
        "calibration_diagnostics": {
            "minimum_pilot_models": 1, "minimum_model_families": 1,
            "minimum_repetitions_per_model_mode": 1,
            "minimum_executed_mutants_per_case": 1,
            "minimum_mutation_kill_rate": 0, "minimum_critical_mutation_kill_rate": 0,
            "reference_maximum_mean_dynamic_X": 1.0,
            "reference_maximum_single_model_dynamic_X": 1.0,
            "minimum_non_degenerate_point_fraction": 0.8,
            "non_degenerate_point_pass_rate_interval": [0.05, 0.95],
            "maximum_absolute_phi_between_distinct_points": 2.0,
        },
    })
    _write(tmp_path / "cases" / "registry.json", {
        "case_families": [
            {"case_id": "calib", "instances": [{"instance_id": "seed-1", "split": "calibration"}]},
            {"case_id": "heldout", "instances": [{"instance_id": "seed-1", "split": "test"}]},
        ],
    })
    # A heldout instance appears in the calibration point-response evidence.
    _write(tmp_path / "cases" / "heldout" / "task" / "tests" / "semantic_checks.json", {"checks": []})
    _write(tmp_path / "cases" / "heldout" / "task" / "tests" / "control_flow_checks.json", {"checks": []})
    evidence = tmp_path / "evidence"
    _write(evidence / "mutation_kill_matrix.json", {
        "rows": [{"case_id": "heldout", "executed": True, "killed_point_ids": [], "target_point_ids": []}],
    })
    _write(evidence / "point_response_matrix.json", {
        "rows": [{
            "case_id": "heldout", "execution_mode": "async",
            "model_id": "m0", "model_family": "f0", "repeat": 0,
            "points": {},
        }],
    })
    report = audit_score_calibration(tmp_path, evidence)
    assert any("non-calibration instances" in gap or "heldout" in gap for gap in report["gaps"])


def test_case_split_map_reads_registry(tmp_path: Path):
    _write(tmp_path / "cases" / "registry.json", {
        "case_families": [
            {"case_id": "calib", "instances": [
                {"instance_id": "a", "split": "calibration"},
                {"instance_id": "b", "split": "calibration"},
            ]},
            {"case_id": "mixed", "instances": [
                {"instance_id": "a", "split": "calibration"},
                {"instance_id": "b", "split": "test"},
            ]},
        ],
    })
    split_map = _case_split_map(tmp_path)
    assert split_map["calib"] == {"calibration"}
    assert split_map["mixed"] == {"calibration", "test"}
