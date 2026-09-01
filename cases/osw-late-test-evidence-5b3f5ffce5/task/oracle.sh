#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/tetris_rotation_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:9219480b-3aed-47fc-8bac-d2cffc5849f7","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

