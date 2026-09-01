#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/chrome_bookmarks_osworld.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"osworld_checkpoint_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:chrome:2ad9387a-65d8-4e33-ad5b-7580065a27ca","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
