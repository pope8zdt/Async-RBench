from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from scripts.validate_track_b import VALIDATION_INSTANCES, run_validation


ROOT = Path(__file__).resolve().parents[1]


def test_validation_script_imports_package_outside_repository_cwd(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_track_b.py"), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "two-case Track B validation" in completed.stdout


def test_validation_report_is_two_case_non_leaderboard(tmp_path: Path) -> None:
    report = run_validation(ROOT, tmp_path / "track-b-validation")

    assert VALIDATION_INSTANCES == (
        "mab-dependency-unblock-8b943d725b::seed-1",
        "mab-late-test-evidence-4c6c77884e::seed-1",
    )
    assert report["case_count"] == 2
    assert report["episode_count"] == 4
    assert report["leaderboard_eligible"] is False
    assert report["validation_kind"] == "engineering_acceptance"
    assert report["model_calls"] == 0
    assert report["docker_started"] is False
    assert report["conformance_passed"] is True
    assert len(report["score_files"]) == 4
    assert (tmp_path / "track-b-validation" / "track-b-validation.json").is_file()
