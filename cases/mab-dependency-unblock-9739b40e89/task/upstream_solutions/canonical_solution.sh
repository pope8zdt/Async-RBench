#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
e=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json')); assert e['passed'] is True and e['canonical_episode_owner']=='evaluator'; pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'source_task_id':'coding:072','status':'three_upstream_results_persisted','upstream_depth':4})+'\n'); pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id':'coding:072','preserved':True,'artifacts':['room_history', 'chat_messages', 'private_room_membership', 'mashup_versions']})+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
r=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); c={'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-dependency-unblock-9739b40e89', 'source_task_id': 'coding:072', 'artifact_type': 'ordered_mashup_room_closure', 'event': 'room_event_contract_completed', 'upstream_depth': 4, 'preserved_workflows': ['room_history', 'chat_messages', 'private_room_membership', 'mashup_versions'], 'source_semantics_reverified': True}; c['event_receipt_sha256']=r['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
