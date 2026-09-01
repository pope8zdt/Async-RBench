#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/snake_collision_test_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:26150609-0da3-4a7d-8868-0faf9c5f01bb","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
