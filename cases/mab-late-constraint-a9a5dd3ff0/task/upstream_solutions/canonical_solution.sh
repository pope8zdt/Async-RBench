#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:024", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["activity_station_identity", "buyer_after_sales_priority", "seller_logistics_priority"], "preserved": true, "source_task_id": "bargaining:024"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-a9a5dd3ff0','source_task_id':'bargaining:024','artifact_type':'infantino_support_closure','event':'warranty_support_terms_delivered','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['activity_station_identity', 'buyer_after_sales_priority', 'seller_logistics_priority'],'authority_applied':True,'selected_terms':{'unit_price': 44.5, 'warranty_months': 24, 'replacement_days': 30, 'delivery_days': 5},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
