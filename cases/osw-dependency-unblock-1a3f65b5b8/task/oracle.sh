#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/steam_cart_osworld.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"osworld_checkpoint_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:chrome:121ba48f-9e17-48ce-9bc6-a4fb17a7ebba","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
