#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/exam_grades_osworld.sh
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:aceb0368-56b8-4073-b70e-3dc9aee184e0","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

