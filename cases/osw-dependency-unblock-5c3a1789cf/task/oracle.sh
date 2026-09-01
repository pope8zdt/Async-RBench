#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/zurich_rental_osworld.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"osworld_checkpoint_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:chrome:1704f00f-79e6-43a7-961b-cedd3724d5fd","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
