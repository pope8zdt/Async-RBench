#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/mail_wallpaper_osworld.sh
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:c2751594-0cd5-4088-be1b-b5f2f9ec97c4","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

