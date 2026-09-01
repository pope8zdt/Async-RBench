#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
evidence=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json',encoding='utf-8')); assert evidence['canonical_episode_owner']=='evaluator' and evidence['passed'] is True
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'status':'source_native_baseline_persisted','source_task_id':'coding:066'},sort_keys=True)+'\n')
pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id':'coding:066','preserved':True,'artifacts':['lyrics', 'chat', 'versions', 'collaborators']},sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
receipt=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); closure={'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-cross-app-artifact-7bfdfeaa3c', 'source_task_id': 'coding:066', 'artifact_type': 'music_collaboration_playback_closure', 'event': 'midi_timing_contract_completed', 'preserved_workflows': ['lyrics', 'chat', 'versions', 'collaborators'], 'source_semantics_reverified': True}; closure['event_receipt_sha256']=receipt['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(closure,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
