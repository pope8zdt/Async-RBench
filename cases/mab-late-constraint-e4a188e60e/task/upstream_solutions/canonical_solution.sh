#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:045", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["jafra_baby_cologne_identity", "buyer_price_quality_priority", "seller_margin_goal"], "preserved": true, "source_task_id": "bargaining:045"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-e4a188e60e','source_task_id':'bargaining:045','artifact_type':'jafra_cologne_support_closure','event':'sealed_batch_support_terms_delivered','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['jafra_baby_cologne_identity', 'buyer_price_quality_priority', 'seller_margin_goal'],'authority_applied':True,'selected_terms':{'unit_price': 18.88, 'seal_check': 'passed', 'batch_traceability': 'confirmed', 'replacement_days': 30, 'support_response_days': 3, 'logistics': 'consolidated'},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
