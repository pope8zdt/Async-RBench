#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/green_background_result_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:gimp:734d6579-c07d-47a8-9ae2-13339795476b","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
