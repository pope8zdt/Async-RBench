#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/daily_mail_report_osworld.sh
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:d9b7c649-c975-4f53-88f5-940b29c47247","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

