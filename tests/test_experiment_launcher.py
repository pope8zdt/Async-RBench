from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_smoke_and_calibration_use_the_official_track() -> None:
    script = (ROOT / "run_calibration.ps1").read_text(encoding="utf-8")
    assert '[ValidateSet("preflight", "smoke", "calibration")]' in script
    assert '"--official-track"' in script
    assert 'if ($Mode -eq "smoke")' in script
    assert '@("--repetitions", "1", "--instances", "secure-release::seed-1")' in script
    assert '$manifestArgs += @("--repetitions", "3")' in script
    assert 'ASYNC_RBENCH_DEEPSEEK_KEY' in script
