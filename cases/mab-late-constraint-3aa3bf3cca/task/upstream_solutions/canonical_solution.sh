#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:030", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["organizer_product_identity", "buyer_price_quality_priority", "seller_production_demand_goal"], "preserved": true, "source_task_id": "bargaining:030"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-3aa3bf3cca','source_task_id':'bargaining:030','artifact_type':'jewelry_organizer_scope_closure','event':'product_quality_scope_clarified','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['organizer_product_identity', 'buyer_price_quality_priority', 'seller_production_demand_goal'],'authority_applied':True,'selected_terms':{'power_requirement': 'none', 'material': 'velvet_ring_holder', 'unit_price': 17.49, 'minimum_batch': 60},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
