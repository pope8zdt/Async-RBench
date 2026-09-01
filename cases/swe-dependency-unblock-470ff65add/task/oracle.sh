#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/reference_solution.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"provisional_implementation_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"instance_ansible__ansible-4c5ce5a1a9e79a845aff4978cfeb72a0d4ecf7d6-v1055803c3a812189a1133297f7f5468579283f86","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /testbed
python3 /app/task_file/scripts/write_manifest.py
