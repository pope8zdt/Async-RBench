#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/mp3_metadata_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:3f05f3b9-29ba-4b6b-95aa-2204697ffc06","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

