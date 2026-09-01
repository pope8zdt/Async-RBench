#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id":"coding:049","status":"provisional","upstream_depth":4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"coding:049","preserved":true,"artifacts":["accounts","group_memberships","chat_history"]}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-311fc423ac','source_task_id':'coding:049','artifact_type':'financial_goal_accounting_closure','event':'accounting_invariants_delivered','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['accounts', 'group_memberships', 'chat_history'],'authority_applied':True,'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
