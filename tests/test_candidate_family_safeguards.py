from pathlib import Path

from async_rbench.cli import _candidate_case_promotion_eligibility


def test_simulated_candidate_family_is_never_promotion_eligible(tmp_path: Path) -> None:
    (tmp_path / "simulation_only.json").write_text(
        '{"simulation_only":true,"promotion_eligible":false}', encoding="utf-8",
    )
    eligible, error = _candidate_case_promotion_eligibility(tmp_path)
    assert eligible is False
    assert "cannot be promoted" in str(error)


def test_candidate_family_without_simulation_marker_reaches_normal_gate(tmp_path: Path) -> None:
    assert _candidate_case_promotion_eligibility(tmp_path) == (True, None)
