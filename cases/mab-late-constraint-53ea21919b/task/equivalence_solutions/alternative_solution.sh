#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:028", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["shirt_product_identity", "buyer_price_quality_priority", "seller_production_demand_goal"], "preserved": true, "source_task_id": "bargaining:028"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-53ea21919b','source_task_id':'bargaining:028','artifact_type':'youth_shirt_production_closure','event':'size_run_capacity_constraint_added','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['shirt_product_identity', 'buyer_price_quality_priority', 'seller_production_demand_goal'],'authority_applied':True,'selected_terms':{'minimum_batch': 120, 'unit_price': 16.5, 'size_run': 'assorted_youth', 'defect_replacement_days': 30},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
