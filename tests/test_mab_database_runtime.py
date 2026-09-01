import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-db"


def test_materialize_refuses_published_cases_and_batch_stays_verified() -> None:
    # The 11 database candidates have since been promoted into cases/registry.json,
    # so re-materialization must fail closed on the immutability guard.
    made = subprocess.run(
        [sys.executable, str(ROOT / "scripts/materialize_mab_database_runtime.py"),
         "--confirm-materialize"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    assert made.returncode != 0
    assert "immutable candidate" in (made.stderr + made.stdout)

    native = subprocess.run([sys.executable, str(ROOT / "scripts/run_mab_database_native_canonical.py")], cwd=ROOT, check=False)
    assert native.returncode == 0
    checked = subprocess.run([sys.executable, str(ROOT / "scripts/verify_mab_database_runtime.py")], cwd=ROOT, check=False)
    assert checked.returncode == 0
    report = json.loads((BATCH / "verification_report.json").read_text(encoding="utf-8"))
    assert report["summary"] == {"case_count": 11, "adapter_verified": 11, "source_native_marble_verified": 11, "native_evaluator_verified": 11}
    for row in report["cases"]:
        assert row["variants"]["oracle_resolution.json"]["exit_code"] == 0
        assert row["variants"]["equivalent_resolution.json"]["exit_code"] == 0
        assert row["variants"]["negative_wrong_diagnosis.json"]["exit_code"] != 0
        assert row["variants"]["negative_ignored_authority.json"]["exit_code"] != 0
