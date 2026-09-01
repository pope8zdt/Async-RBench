#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/slide_background_osworld.sh
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:47f7c0ce-a5fb-4100-a5e6-65cd0e7429e5","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

