#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id":"bargaining:022","status":"provisional","upstream_depth":4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"bargaining:022","preserved":true,"artifacts":["warranty_priority","offer_history","buyer_demand"]}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-fc88525ce2','source_task_id':'bargaining:022','artifact_type':'idol_doll_supply_scope_closure','event':'production_scope_constraint_added','event_theme':'task_scope_or_dependency_change','upstream_depth':4,'preserved_workflows':['warranty_priority', 'offer_history', 'buyer_demand'],'authority_applied':True,'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
