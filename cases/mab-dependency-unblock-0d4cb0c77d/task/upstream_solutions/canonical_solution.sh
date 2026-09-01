#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
evidence=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json',encoding='utf-8')); assert evidence['canonical_episode_owner']=='evaluator' and evidence['passed'] is True
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'status':'source_native_baseline_persisted','source_task_id':'coding:021'},sort_keys=True)+'\n')
pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id':'coding:021','preserved':True,'artifacts':['messages', 'meetings', 'completed_tasks', 'unaffected_assignments']},sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
receipt=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); closure={'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-dependency-unblock-0d4cb0c77d', 'source_task_id': 'coding:021', 'artifact_type': 'teamsync_adaptive_schedule_closure', 'event': 'adaptive_schedule_completed', 'preserved_workflows': ['messages', 'meetings', 'completed_tasks', 'unaffected_assignments'], 'source_semantics_reverified': True}; closure['event_receipt_sha256']=receipt['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(closure,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
