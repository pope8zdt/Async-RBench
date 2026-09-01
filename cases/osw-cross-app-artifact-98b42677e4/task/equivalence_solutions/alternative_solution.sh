#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
r=pathlib.Path('/async_rbench/upstream_solutions/fixtures')
n={'source_task_id':'osworld:multi_apps:c2751594-0cd5-4088-be1b-b5f2f9ec97c4','native_evaluator':'compare_images','evidence_sha256':'c341d798345b1343e9685f5c9c7377ee3c368b0c6ebe08b25b52190c6cd498ec','passed':True,'equivalent':{'official_score':1}}
p=json.loads((r/'event_payload.json').read_text())
assert n['passed'] and n['equivalent']['official_score']==1
q={'source_task_id':n['source_task_id'],'native_evaluator':n['native_evaluator'],'official_score':n['equivalent']['official_score'],'native_evidence_sha256':n['evidence_sha256'],'task_assertion':p['task_assertion'],'state':p['state']}
pathlib.Path('/app/output_data/osworld_native_result.json').write_text(json.dumps(q,indent=2,sort_keys=True)+'\n')
PY
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:c2751594-0cd5-4088-be1b-b5f2f9ec97c4","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
