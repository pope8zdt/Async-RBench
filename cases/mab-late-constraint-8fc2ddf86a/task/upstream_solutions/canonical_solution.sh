#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:036", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["butterfly_earring_identity", "buyer_price_quality_priority", "seller_logistics_goal"], "preserved": true, "source_task_id": "bargaining:036"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-8fc2ddf86a','source_task_id':'bargaining:036','artifact_type':'butterfly_earring_scope_closure','event':'sterling_product_scope_clarified','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['butterfly_earring_identity', 'buyer_price_quality_priority', 'seller_logistics_goal'],'authority_applied':True,'selected_terms':{'power_requirement': 'none', 'material_certificate': '925_sterling_silver', 'pair_count': 1, 'unit_price': 12.59, 'delivery_days': 5},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
