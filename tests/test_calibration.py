from pathlib import Path

from async_rbench.evaluation.calibration import audit_score_calibration


ROOT = Path(__file__).resolve().parents[1]


def test_calibration_fails_closed_without_executed_evidence(tmp_path: Path) -> None:
    report = audit_score_calibration(ROOT, tmp_path)
    assert report["cases"] == {}
    assert any("mutation" in gap for gap in report["gaps"])
    assert any("point-response" in gap for gap in report["gaps"])
