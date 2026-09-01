#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:033", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["ribbed_jumpsuit_identity", "buyer_scalability_priority", "seller_logistics_goal"], "preserved": true, "source_task_id": "bargaining:033"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data'); r=json.loads((O/'event_receipt.json').read_text())
c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-5aedbb79af','source_task_id':'bargaining:033','artifact_type':'yoga_jumpsuit_assortment_closure','event':'assortment_capacity_scope_added','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['ribbed_jumpsuit_identity', 'buyer_scalability_priority', 'seller_logistics_goal'],'authority_applied':True,'selected_terms':{'minimum_batch': 100, 'unit_price': 25.49, 'size_run': 'XS-XL', 'color_count': 4, 'lead_time_days': 14},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']}
(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
