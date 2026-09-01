#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/workspace_setup_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:48c46dc7-fe04-4505-ade7-723cba1aa6f6","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

