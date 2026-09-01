#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id":"bargaining:012","status":"provisional","upstream_depth":3}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"bargaining:012","preserved":true,"artifacts":["quality_requirement","offer_history","buyer_cost_goal"]}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-f395d7243c','source_task_id':'bargaining:012','artifact_type':'seal_protectant_logistics_closure','event':'logistics_tiers_countered','event_theme':'late_or_out_of_order_superseded_result','upstream_depth':3,'preserved_workflows':['quality_requirement', 'offer_history', 'buyer_cost_goal'],'authority_applied':True,'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
