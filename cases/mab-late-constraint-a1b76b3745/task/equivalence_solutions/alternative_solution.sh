#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:034", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["delay_spray_identity", "buyer_condition_priority", "seller_production_demand_goal"], "preserved": true, "source_task_id": "bargaining:034"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-a1b76b3745','source_task_id':'bargaining:034','artifact_type':'delay_spray_condition_scope_closure','event':'sealed_lot_scope_clarified','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['delay_spray_identity', 'buyer_condition_priority', 'seller_production_demand_goal'],'authority_applied':True,'selected_terms':{'power_requirement': 'none', 'condition_evidence': 'sealed_lot_certificate', 'shelf_life_months': 24, 'unit_price': 17.5, 'minimum_batch': 60, 'delivery_days': 5},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
