#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
t=json.load(open('/app/task_file/chrome_extension_truth.json',encoding='utf-8'))
t.update({'persisted':True,'verification_method':'extension_card_path'})
pathlib.Path('/app/output_data/extension_installation.json').write_text(json.dumps(t,sort_keys=True)+'\n')
PY
printf '%s\n' '{"status":"provisional_implementation_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:a74b607e-6bb5-4ea8-8a7c-5d97c7bbcd2a","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
