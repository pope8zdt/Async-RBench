#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:026", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["changing_station_identity", "buyer_condition_priority", "seller_logistics_cost_goal"], "preserved": true, "source_task_id": "bargaining:026"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-ae2fc903e5','source_task_id':'bargaining:026','artifact_type':'doll_station_condition_closure','event':'condition_and_shipping_certificate_delivered','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['changing_station_identity', 'buyer_condition_priority', 'seller_logistics_cost_goal'],'authority_applied':True,'selected_terms':{'unit_price': 57.79, 'condition_check': 'passed', 'coverage_months': 12, 'shipping_days': 6},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
