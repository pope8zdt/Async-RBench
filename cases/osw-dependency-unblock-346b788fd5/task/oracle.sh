#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/dog_layer_resize_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:gimp:d16c99dc-2a1e-46f2-b350-d97c86c85c15","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
