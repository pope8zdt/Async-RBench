#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/reference_solution.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"provisional_implementation_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"clap-rs__clap-3179","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /testbed
python3 /app/task_file/scripts/write_manifest.py
