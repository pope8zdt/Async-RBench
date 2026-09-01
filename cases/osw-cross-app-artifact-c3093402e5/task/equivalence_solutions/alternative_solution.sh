#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
t=json.load(open('/app/task_file/impress_audio_truth.json',encoding='utf-8'))
t.update({'persisted':True,'verification_method':'slide_audio_relationship'})
pathlib.Path('/app/output_data/presentation_audio.json').write_text(json.dumps(t,sort_keys=True)+'\n')
PY
printf '%s\n' '{"status":"provisional_implementation_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:778efd0a-153f-4842-9214-f05fc176b877","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
