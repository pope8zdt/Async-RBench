#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/osworld_native_solution.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"provisional_implementation_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:778efd0a-153f-4842-9214-f05fc176b877","preserved":true,"prior_state":"target slideshow is open in Impress"}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
