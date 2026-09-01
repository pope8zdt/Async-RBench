#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:041", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["ladybug_plush_identity", "buyer_warranty_priority", "seller_production_demand_goal"], "preserved": true, "source_task_id": "bargaining:041"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-5837bf15f5','source_task_id':'bargaining:041','artifact_type':'ladybug_plush_safety_scope_closure','event':'plush_safety_scope_clarified','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['ladybug_plush_identity', 'buyer_warranty_priority', 'seller_production_demand_goal'],'authority_applied':True,'selected_terms':{'power_requirement': 'none', 'material_check': 'child_safe_plush', 'seam_test': 'passed', 'unit_price': 13.99, 'minimum_batch': 60, 'replacement_days': 30},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
