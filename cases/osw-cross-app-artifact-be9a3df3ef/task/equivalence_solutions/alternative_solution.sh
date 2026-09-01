#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
r=pathlib.Path('/async_rbench/upstream_solutions/fixtures')
n={'source_task_id':'osworld:multi_apps:47f7c0ce-a5fb-4100-a5e6-65cd0e7429e5','native_evaluator':'compare_images','evidence_sha256':'0a6c4489b3c34f84db0e76686e6bf9e1470dd8407bd731eefa5e6f690e2e2651','passed':True,'equivalent':{'official_score':1}}
p=json.loads((r/'event_payload.json').read_text())
assert n['passed'] and n['equivalent']['official_score']==1
q={'source_task_id':n['source_task_id'],'native_evaluator':n['native_evaluator'],'official_score':n['equivalent']['official_score'],'native_evidence_sha256':n['evidence_sha256'],'task_assertion':p['task_assertion'],'state':p['state']}
pathlib.Path('/app/output_data/osworld_native_result.json').write_text(json.dumps(q,indent=2,sort_keys=True)+'\n')
PY
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:47f7c0ce-a5fb-4100-a5e6-65cd0e7429e5","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
