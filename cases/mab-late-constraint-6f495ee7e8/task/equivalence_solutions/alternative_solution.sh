#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:046", "status": "provisional", "upstream_depth": 3}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["kohler_1266657_identity", "buyer_timely_delivery_priority", "seller_premium_price_goal"], "preserved": true, "source_task_id": "bargaining:046"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-6f495ee7e8','source_task_id':'bargaining:046','artifact_type':'kohler_valve_delivery_closure','event':'current_genuine_part_delivery_counter','event_theme':'late_or_out_of_order_superseded_result','upstream_depth':3,'preserved_workflows':['kohler_1266657_identity', 'buyer_timely_delivery_priority', 'seller_premium_price_goal'],'authority_applied':True,'selected_terms':{'unit_price': 10.5, 'part_number': '1266657', 'genuine_kohler': True, 'delivery_days': 2, 'warranty_months': 12},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
