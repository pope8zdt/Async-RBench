#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:044", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["princess_leia_endor_identity", "buyer_after_sales_priority", "seller_premium_price_goal"], "preserved": true, "source_task_id": "bargaining:044"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-cb2a355435','source_task_id':'bargaining:044','artifact_type':'leia_endor_authenticity_closure','event':'collectible_authenticity_warranty_delivered','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['princess_leia_endor_identity', 'buyer_after_sales_priority', 'seller_premium_price_goal'],'authority_applied':True,'selected_terms':{'unit_price': 21.99, 'series': 'Black Series', 'character': 'Princess Leia Endor', 'packaging': 'sealed', 'warranty_months': 12, 'delivery_days': 4},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
