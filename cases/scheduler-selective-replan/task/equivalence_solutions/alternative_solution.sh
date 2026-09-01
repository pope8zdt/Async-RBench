#!/bin/bash
set -euo pipefail
python3 /async_rbench/upstream_solutions/alternative_solution.py
python3 /app/task_file/scripts/validate_plan.py \
  --requests-bucket1 /app/task_file/input_data/requests_bucket_1.jsonl \
  --requests-bucket2 /app/task_file/input_data/requests_bucket_2.jsonl \
  --plan-b1 /app/task_file/output_data/plan_b1.jsonl \
  --plan-b2 /app/task_file/output_data/plan_b2.jsonl \
  --shape-budget 8 \
  --out /app/task_file/output_data/alternative_validation_report.json
python3 - <<'PY'
import hashlib, json
from pathlib import Path
out = Path('/app/task_file/output_data')
report = json.loads((out / 'alternative_validation_report.json').read_text())
authority = json.loads(Path('/app/task_file/events/bucket2_authority.json').read_text())['authority_receipt']
target = out / 'validator_reports'
target.mkdir(parents=True, exist_ok=True)
for item in report['results']:
    number = 1 if item['bucket'] == 'bucket1' else 2
    payload = {**item, 'plan_revision': hashlib.sha256((out / f'plan_b{number}.jsonl').read_bytes()).hexdigest()}
    if number == 2:
        payload['authority_receipt'] = authority
    (target / f'bucket{number}.json').write_text(json.dumps(payload, indent=2) + '\n')
PY
python3 /app/task_file/scripts/write_manifest.py
