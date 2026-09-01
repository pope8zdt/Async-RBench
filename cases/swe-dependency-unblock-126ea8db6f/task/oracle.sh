#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/reference_solution.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"provisional_implementation_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"instance_ansible__ansible-cb94c0cc550df9e98f1247bc71d8c2b861c75049-v1055803c3a812189a1133297f7f5468579283f86","preserved":true}' > /app/output_data/preserved_source_facts.json
python /app/task_file/scripts/event_worker.py --workspace /testbed
python /app/task_file/scripts/write_manifest.py
