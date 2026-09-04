from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from async_rbench import cli
from async_rbench.experiment_plan import validate_frozen_release
from async_rbench.evaluation.calibration import audit_score_calibration, _case_split_map


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _frozen_contract() -> dict:
    return {
        "version": "11.0.0",
        "status": "frozen",
    }


def _frozen_dataset() -> dict:
    return {"schema_version": "1.0", "status": "publication_locked"}


def test_live_v11_release_passes_freeze_gate():
    assert validate_frozen_release(ROOT) == []


def test_freeze_accepts_frozen_release(tmp_path: Path):
    _write(tmp_path / "evaluation_contract.json", _frozen_contract())
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    assert validate_frozen_release(tmp_path) == []


def test_freeze_rejects_dev_version(tmp_path: Path):
    contract = _frozen_contract()
    contract["version"] = "9.1.0-dev"
    _write(tmp_path / "evaluation_contract.json", contract)
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    assert any("non-dev" in error for error in validate_frozen_release(tmp_path))


def test_freeze_rejects_non_frozen_contract(tmp_path: Path):
    contract = _frozen_contract()
    contract["status"] = "development"
    _write(tmp_path / "evaluation_contract.json", contract)
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    assert any("must be 'frozen'" in error for error in validate_frozen_release(tmp_path))


def test_freeze_rejects_pre_calibration_dataset(tmp_path: Path):
    _write(tmp_path / "evaluation_contract.json", _frozen_contract())
    _write(tmp_path / "dataset_policy.json", {
        "schema_version": "1.0",
        "status": "pre_calibration_locked",
    })
    assert any("release-locked" in error for error in validate_frozen_release(tmp_path))


def test_freeze_does_not_require_calibration_audit(tmp_path: Path):
    _write(tmp_path / "evaluation_contract.json", _frozen_contract())
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    assert validate_frozen_release(tmp_path) == []


def test_freeze_does_not_require_model_panel(tmp_path: Path):
    _write(tmp_path / "evaluation_contract.json", _frozen_contract())
    _write(tmp_path / "dataset_policy.json", _frozen_dataset())
    _write(tmp_path / "configs" / "calibration-plan.json", {
        "model_panel": [{"model_id": "m0", "model_family": "f0"}],
    })
    assert validate_frozen_release(tmp_path) == []


def test_cli_release_mode_executes_frozen_release_gate(monkeypatch):
    monkeypatch.setattr(cli, "discover_cases", lambda _root: [])
    monkeypatch.setattr(cli, "discover_case_instances", lambda _root: [])
    for name in (
        "validate_sources",
        "validate_evaluation_contract",
        "validate_event_taxonomy",
        "validate_event_theme_fixtures",
        "validate_semantic_registries",
        "validate_mutation_manifest",
        "validate_dataset_policy",
        "validate_calibration_plan",
        "validate_release_security",
        "validate_case_registry",
    ):
        monkeypatch.setattr(cli, name, lambda *_args, **_kwargs: [])
    calls = []
    monkeypatch.setattr(cli, "validate_frozen_release", lambda root: calls.append(root) or [])

    assert cli.cmd_validate(SimpleNamespace(release=True)) == 0
    assert calls == [cli.ROOT]


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
