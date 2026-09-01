#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:023", "status": "provisional", "upstream_depth": 3}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["ps4_compatibility", "original_price_reference", "buyer_quality_priority"], "preserved": true, "source_task_id": "bargaining:023"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-99180ff520','source_task_id':'bargaining:023','artifact_type':'hasbro_ps4_fulfillment_closure','event':'verified_delivery_quality_counter','event_theme':'late_or_out_of_order_superseded_result','upstream_depth':3,'preserved_workflows':['ps4_compatibility', 'original_price_reference', 'buyer_quality_priority'],'authority_applied':True,'selected_terms':{'unit_price': 14.25, 'condition': 'new', 'delivery_days': 3, 'quality_rating': 4.5},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
