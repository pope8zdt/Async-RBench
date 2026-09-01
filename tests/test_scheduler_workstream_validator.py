from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_public_scheduler_validator_emits_self_consistent_per_bucket_facts(
    tmp_path: Path,
) -> None:
    source = ROOT / "cases" / "scheduler-selective-replan" / "task" / "task_file"
    task_file = tmp_path / "task_file"
    shutil.copytree(source, task_file)
    scripts = task_file / "scripts"
    subprocess.run([sys.executable, str(scripts / "baseline_packer.py")], check=True)
    report_path = tmp_path / "combined.json"
    result = subprocess.run([
        sys.executable, str(scripts / "validate_plan.py"),
        "--requests-bucket1", str(task_file / "input_data" / "requests_bucket_1.jsonl"),
        "--requests-bucket2", str(task_file / "input_data" / "requests_bucket_2.jsonl"),
        "--plan-b1", str(task_file / "output_data" / "plan_b1.jsonl"),
        "--plan-b2", str(task_file / "output_data" / "plan_b2.jsonl"),
        "--shape-budget", "8", "--out", str(report_path),
    ], check=False, capture_output=True, text=True)
    assert result.returncode in {0, 1}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    by_bucket = {item["bucket"]: item for item in report["results"]}
    assert set(by_bucket) == {"bucket1", "bucket2"}
    for item in by_bucket.values():
        assert re.fullmatch(r"[0-9a-f]{64}", item["plan_revision"])
        assert isinstance(item["passes"], bool)
        assert {"cost", "pad_ratio"} <= set(item["metrics"])
    assert re.fullmatch(
        r"sc-bucket2-authority-[0-9a-f]{16}",
        by_bucket["bucket2"]["authority_receipt"],
    )
