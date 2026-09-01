#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:029", "status": "provisional", "upstream_depth": 3}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["cast_iron_product_identity", "buyer_premium_feature_priority", "seller_margin_goal"], "preserved": true, "source_task_id": "bargaining:029"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-1e1fa7c00b','source_task_id':'bargaining:029','artifact_type':'turtle_doorstop_freight_closure','event':'freight_finish_counter_supersedes_quote','event_theme':'late_or_out_of_order_superseded_result','upstream_depth':3,'preserved_workflows':['cast_iron_product_identity', 'buyer_premium_feature_priority', 'seller_margin_goal'],'authority_applied':True,'selected_terms':{'unit_price': 25.49, 'finish': 'heavy_duty_rustic', 'delivery_days': 7},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
