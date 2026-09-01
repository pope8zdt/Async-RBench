#!/usr/bin/env bash
set -euo pipefail
# Benchmark-maintenance oracle: produce the correct combined plan for both
# buckets, then verify it with the shared public validator.
python3 /async_rbench/upstream_solutions/reference_packer.py --task-root /app/task_file
python3 /app/task_file/scripts/validate_plan.py \
  --requests-bucket1 /app/task_file/input_data/requests_bucket_1.jsonl \
  --requests-bucket2 /app/task_file/input_data/requests_bucket_2.jsonl \
  --plan-b1 /app/task_file/output_data/plan_b1.jsonl \
  --plan-b2 /app/task_file/output_data/plan_b2.jsonl \
  --shape-budget 8 \
  --out /app/task_file/output_data/oracle_validation_report.json
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

out = Path("/app/task_file/output_data")
report = json.loads((out / "oracle_validation_report.json").read_text(encoding="utf-8"))
reports = out / "validator_reports"
reports.mkdir(parents=True, exist_ok=True)
for item in report["results"]:
    number = 1 if item["bucket"] == "bucket1" else 2
    plan = out / f"plan_b{number}.jsonl"
    payload = {
        **item,
        "plan_revision": hashlib.sha256(plan.read_bytes()).hexdigest(),
    }
    if number == 2:
        payload["authority_receipt"] = json.loads(
            Path("/app/task_file/events/bucket2_authority.json").read_text(encoding="utf-8")
        )["authority_receipt"]
    (reports / f"bucket{number}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
PY
python3 /app/task_file/scripts/write_manifest.py
