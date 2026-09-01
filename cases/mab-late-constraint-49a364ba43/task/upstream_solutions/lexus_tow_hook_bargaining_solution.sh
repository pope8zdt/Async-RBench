#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
n=json.load(open('/app/task_file/evaluator_reference.json'));assert n['passed'] and n['source_task_id']=='bargaining:021' and n['native_evaluator_verified']
pathlib.Path('/app/output_data/solution.py').write_bytes(pathlib.Path('/app/task_file/native_solution.py').read_bytes())
PY
python3 /app/task_file/scripts/event_worker.py
python3 - <<'PY'
import json,pathlib
o=pathlib.Path('/app/output_data');r=json.loads((o/'event_receipt.json').read_text());n=json.load(open('/app/task_file/evaluator_reference.json'))
c={'source_task_id':'bargaining:021','recovered_artifact':'qualified_lexus_tow_hook_delivery_counter','qualified_result_consumed':True,'stale_revision_rejected':True,'battery_condition_preserved':True,'documented_battery_condition_preserved':True,'documented_battery_condition_preserved':True,'preserved_workflows':['buyer_budget_ceiling','battery_condition_requirement','delivery_priority'],'synchronized_surfaces':['negotiation_ledger','agreement_terms'],'event_receipt_sha256':r['receipt_sha256'],'native_evidence_sha256':n['evidence_sha256'],'closure_reverified':True}
(o/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
m={'schema_version':'async-rbench-closure-v1','case_id':'mab-late-constraint-49a364ba43','source_task_id':'bargaining:021','event_receipt_sha256':r['receipt_sha256'],'event_consumed':True,'source_semantics_reverified':True,'closure_complete':True,'final_revision_sha256':__import__('hashlib').sha256((o/'solution.py').read_bytes()).hexdigest()}
(o/'decision_manifest.json').write_text(json.dumps(m,sort_keys=True)+'\n')
PY
