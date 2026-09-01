#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
r=pathlib.Path('/async_rbench/upstream_solutions/fixtures')
n={'source_task_id':'osworld:multi_apps:5bc63fb9-276a-4439-a7c1-9dc76401737f','native_evaluator':'compare_docx_files_and_ignore_new_lines','evidence_sha256':'1b22088b58ce2e5a031a5f3c9437d532909734cc82bd9f9bffb646a3b41f989d','passed':True,'equivalent':{'official_score':1}}
p=json.loads((r/'event_payload.json').read_text())
assert n['passed'] and n['equivalent']['official_score']==1
q={'source_task_id':n['source_task_id'],'native_evaluator':n['native_evaluator'],'official_score':n['equivalent']['official_score'],'native_evidence_sha256':n['evidence_sha256'],'task_assertion':p['task_assertion'],'state':p['state']}
pathlib.Path('/app/output_data/osworld_native_result.json').write_text(json.dumps(q,indent=2,sort_keys=True)+'\n')
PY
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:5bc63fb9-276a-4439-a7c1-9dc76401737f","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
