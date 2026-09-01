#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:038", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["halloween_collar_identity", "buyer_scalability_priority", "seller_margin_goal"], "preserved": true, "source_task_id": "bargaining:038"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-32f347d363','source_task_id':'bargaining:038','artifact_type':'cat_bowtie_collar_scope_closure','event':'collar_feature_scope_clarified','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['halloween_collar_identity', 'buyer_scalability_priority', 'seller_margin_goal'],'authority_applied':True,'selected_terms':{'power_requirement': 'none', 'two_pack': True, 'adjustable': True, 'bell_included': True, 'minimum_batch': 120, 'unit_price': 7.95, 'lead_time_days': 10},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
