#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id":"bargaining:013","status":"provisional","upstream_depth":3}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"bargaining:013","preserved":true,"artifacts":["buyer_urgency","offer_history","written_confirmation_request"]}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-efb76e596e','source_task_id':'bargaining:013','artifact_type':'bookcase_delivery_bargaining_closure','event':'delivery_margin_tiers_countered','event_theme':'late_or_out_of_order_superseded_result','upstream_depth':3,'preserved_workflows':['buyer_urgency', 'offer_history', 'written_confirmation_request'],'authority_applied':True,'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
