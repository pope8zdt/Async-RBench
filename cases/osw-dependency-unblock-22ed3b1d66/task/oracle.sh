#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/vlc_persistence_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:vlc:5ac2891a-eacd-4954-b339-98abba077adb","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
