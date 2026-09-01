#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:043", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["wooden_bead_product_identity", "buyer_scalability_priority", "seller_production_demand_goal"], "preserved": true, "source_task_id": "bargaining:043"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-637224fe05','source_task_id':'bargaining:043','artifact_type':'wooden_bead_capacity_closure','event':'bead_capacity_scope_added','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['wooden_bead_product_identity', 'buyer_scalability_priority', 'seller_production_demand_goal'],'authority_applied':True,'selected_terms':{'pack_count': 100, 'diameter_inches': 0.75, 'finish': 'unfinished_natural_wood', 'minimum_packs': 80, 'unit_price': 7.35, 'lead_time_days': 7},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
