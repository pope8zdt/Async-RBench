#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/alternative_solution.py /app/output_data/solution.py
printf '%s\n' '{"source_task_id":"coding:033","status":"provisional","upstream_depth":4}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"coding:033","preserved":true,"artifacts":["session_acl","presence","chat_history","editing_actions"]}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py
python3 - <<'PY'
import json,pathlib
O=pathlib.Path('/app/output_data');r=json.loads((O/'event_receipt.json').read_text());c={'schema_version':'async-rbench-source-closure-v1','case_id':'mab-late-constraint-3a268eae01','source_task_id':'coding:033','artifact_type':'photo_collaboration_revision_closure','event':'synchronization_contract_delivered','event_theme':'delayed_authoritative_result','upstream_depth':4,'preserved_workflows':['session_acl', 'presence', 'chat_history', 'editing_actions'],'authority_applied':True,'source_semantics_reverified':True,'event_receipt_sha256':r['receipt_sha256']};(O/'coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
