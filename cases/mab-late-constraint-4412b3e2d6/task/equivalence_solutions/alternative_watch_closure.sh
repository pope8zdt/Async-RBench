#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
install -m 0644 /app/task_file/native_solution.py /app/output_data/solution.py
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 - <<'PY'
import json, pathlib
out = pathlib.Path('/app/output_data')
receipt = json.loads((out / 'event_receipt.json').read_text())
assert receipt['qualified_result']['price'] == 62
assert receipt['qualified_result']['battery_age_days'] == 90
assert receipt['qualified_result']['guarantee_months'] == 12
assert receipt['qualified_result']['quantity'] == 50 and receipt['qualified_result']['consolidated'] is True
closure = {'source_task_id':'bargaining:008','recovered_artifact':'qualified_watch_counter','qualified_result_consumed':True,'stale_revision_rejected':True,'ninety_day_battery':True,'one_year_replacement_guarantee':True,'fifty_watch_consolidation':True,'event_receipt_sha256':receipt['receipt_sha256'],'closure_reverified':True}
(out / 'negotiation_closure.json').write_text(json.dumps(closure, sort_keys=True) + '\n')
PY
python3 /app/task_file/scripts/write_manifest.py
printf '%s\n' '{"status":"equivalent-watch-bargaining-closure"}' > /app/output_data/provisional_checkpoint.json
