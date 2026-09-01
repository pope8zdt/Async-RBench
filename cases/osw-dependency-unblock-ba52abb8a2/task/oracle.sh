#!/bin/bash
set -euo pipefail
 bash /async_rbench/upstream_solutions/extension_preference_oracle.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"provisional_implementation_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:chrome:6766f2b8-8a72-417f-a9e5-56fcaa735837","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
