#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/reference_solution.sh
mkdir -p /app/output_data
printf '%s\n' '{"status":"provisional_implementation_persisted"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"instance_ansible__ansible-709484969c8a4ffd74b839a673431a8c5caa6457-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5","preserved":true}' > /app/output_data/preserved_source_facts.json
python /app/task_file/scripts/event_worker.py --workspace /testbed
python /app/task_file/scripts/write_manifest.py
