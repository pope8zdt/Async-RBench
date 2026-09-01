#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id": "bargaining:040", "status": "provisional", "upstream_depth": 4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"artifacts": ["two_piece_keychain_identity", "buyer_after_sales_priority", "seller_long_term_contract_goal"], "preserved": true, "source_task_id": "bargaining:040"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-d8248233eb','source_task_id':'bargaining:040','artifact_type':'keychain_support_contract_closure','event':'warranty_contract_terms_delivered','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['two_piece_keychain_identity', 'buyer_after_sales_priority', 'seller_long_term_contract_goal'],'authority_applied':True,'selected_terms':{'two_piece_set': True, 'unit_price': 7.5, 'warranty_months': 24, 'support_response_days': 2, 'contract_months': 12},'tool_sequence':['offer','authority','counter','finalize'],'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
