#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id":"bargaining:010","status":"provisional","upstream_depth":4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"bargaining:010","preserved":true,"artifacts":["buyer_quality_requirement","trial_plan","offer_history"]}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-test-evidence-11ad0b6722','source_task_id':'bargaining:010','artifact_type':'ohp_film_quality_contract_closure','event':'quality_evidence_and_contract_tier_delivered','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['buyer_quality_requirement', 'trial_plan', 'offer_history'],'authority_applied':True,'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
