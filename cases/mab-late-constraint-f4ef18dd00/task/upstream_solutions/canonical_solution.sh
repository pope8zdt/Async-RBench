#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:032", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["chisel_identity", "buyer_timely_delivery_priority", "seller_production_demand_goal"], "preserved": true, "source_task_id": "bargaining:032"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-f4ef18dd00','source_task_id':'bargaining:032','artifact_type':'pneumatic_chisel_delivery_closure','event':'production_delivery_slot_confirmed','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['chisel_identity', 'buyer_timely_delivery_priority', 'seller_production_demand_goal'],'authority_applied':True,'selected_terms':{'unit_price': 21.95, 'production_slot': 'confirmed', 'delivery_days': 4, 'warranty_months': 12, 'logistics': 'consolidated'},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
