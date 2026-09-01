#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/bookkeeping_osworld.sh
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:8e116af7-7db7-4e35-a68b-b0939c066c78","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

