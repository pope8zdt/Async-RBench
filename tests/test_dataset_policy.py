from __future__ import annotations

import json
from pathlib import Path

from async_rbench.dataset_policy import (
    build_dataset_audit, difficulty_profile, load_dataset_policy, validate_dataset_policy,
)
from async_rbench.experiment_plan import validate_calibration_plan, validate_release_security
from async_rbench.spec import discover_case_instances


ROOT = Path(__file__).resolve().parents[1]


def test_dataset_policy_is_internally_consistent() -> None:
    assert validate_dataset_policy(ROOT) == []


def test_dataset_policy_cannot_disable_a_quality_gate(tmp_path: Path) -> None:
    policy = load_dataset_policy(ROOT)
    policy["acceptance"]["requires_source_instruction_fidelity"] = False
    (tmp_path / "dataset_policy.json").write_text(json.dumps(policy), encoding="utf-8")
    errors = validate_dataset_policy(tmp_path)
    assert any("requires_source_instruction_fidelity must be true" in error for error in errors)


def test_registered_seed_set_has_splits_and_matching_structural_difficulty() -> None:
    report = build_dataset_audit(ROOT, discover_case_instances(ROOT))
    assert report["static_valid"] is True
    assert report["registered_instance_count"] == 201
    assert report["counts"]["splits"] == {"calibration": 82, "development": 30, "test": 89}
    # The 200-family / 201-instance dataset is frozen: every registered instance
    # carries a transformed-case quality contract and the audit gate passes.
    assert report["expansion_complete"] is True
    assert report["quality_contract_complete"] is True
    assert report["publication_ready"] is True
    assert report["quality_errors"] == []
    assert sum(row["quality_contract_passed"] is True for row in report["rows"]) == 201


def test_difficulty_profile_is_deterministic() -> None:
    policy = load_dataset_policy(ROOT)
    case = discover_case_instances(ROOT)[0].load()
    assert difficulty_profile(case, policy) == difficulty_profile(case, policy)
    assert difficulty_profile(case, policy)["label"] in {"easy", "medium", "hard"}


def test_calibration_plan_matches_evaluation_contract_and_real_profiles() -> None:
    assert validate_calibration_plan(ROOT) == []


def test_release_security_excludes_local_credential_files() -> None:
    assert validate_release_security(ROOT) == []
