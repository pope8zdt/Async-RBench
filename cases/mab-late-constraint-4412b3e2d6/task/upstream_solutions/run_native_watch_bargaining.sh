#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /app/task_file/native_solution.py /app/output_data/solution.py
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 - <<'PY'
import json, pathlib
out = pathlib.Path('/app/output_data')
receipt = json.loads((out / 'event_receipt.json').read_text())
terms = receipt['qualified_result']
assert terms == {'price': 62, 'battery_age_days': 90, 'guarantee_months': 12, 'quantity': 50, 'consolidated': True}
closure = {
  'source_task_id': 'bargaining:008',
  'recovered_artifact': 'qualified_watch_counter',
  'qualified_result_consumed': True,
  'stale_revision_rejected': True,
  'ninety_day_battery': True,
  'one_year_replacement_guarantee': True,
  'fifty_watch_consolidation': True,
  'event_receipt_sha256': receipt['receipt_sha256'],
  'closure_reverified': True,
}
(out / 'negotiation_closure.json').write_text(json.dumps(closure, sort_keys=True) + '\n')
PY
python3 /app/task_file/scripts/write_manifest.py
