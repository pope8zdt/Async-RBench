#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/nba_store_osworld.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"osworld_checkpoint_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:chrome:9f3f70fc-5afc-4958-a7b7-3bb4fcb01805","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
