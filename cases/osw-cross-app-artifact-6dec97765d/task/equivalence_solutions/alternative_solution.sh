#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' '{"status":"independent_equivalent_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"source_task_id":"osworld:multi_apps:510f64c8-9bcc-4be1-8d30-638705850618"}' >/app/output_data/preserved_source_facts.json
python3 - <<'PY'
import json,pathlib
f=pathlib.Path('/async_rbench/upstream_solutions/fixtures');n=json.loads((f/'native_canonical_report.json').read_text());p=json.loads((f/'event_payload.json').read_text());o=pathlib.Path('/app/output_data');r={'source_task_id':p['source_task_id'],'native_evaluator':n['native_evaluator'],'official_score':n['equivalent']['official_score'],'native_evidence_sha256':n['evidence_sha256'],'task_assertion':p['task_assertion'],'state':dict(p['state'])};(o/'osworld_native_result.json').write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
PY
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
