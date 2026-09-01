#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/chrome_dnt_osworld.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"osworld_checkpoint_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:chrome:030eeff7-b492-4218-b312-701ec99ee0cc","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
