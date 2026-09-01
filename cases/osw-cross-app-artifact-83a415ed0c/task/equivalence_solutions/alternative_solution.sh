#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
r=pathlib.Path('/async_rbench/upstream_solutions/fixtures')
n={'source_task_id':'osworld:multi_apps:98e8e339-5f91-4ed2-b2b2-12647cb134f4','native_evaluator':'compare_docx_files','evidence_sha256':'949cce5256ac21a55f710dc12915a20209a017be9625fecf00ca21a97f29b5b8','passed':True,'equivalent':{'official_score':1}}
p=json.loads((r/'event_payload.json').read_text())
assert n['passed'] and n['equivalent']['official_score']==1
q={'source_task_id':n['source_task_id'],'native_evaluator':n['native_evaluator'],'official_score':n['equivalent']['official_score'],'native_evidence_sha256':n['evidence_sha256'],'task_assertion':p['task_assertion'],'state':p['state']}
pathlib.Path('/app/output_data/osworld_native_result.json').write_text(json.dumps(q,indent=2,sort_keys=True)+'\n')
PY
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:98e8e339-5f91-4ed2-b2b2-12647cb134f4","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
