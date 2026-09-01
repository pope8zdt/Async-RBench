#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/ssh_account_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:os:5812b315-e7bd-4265-b51f-863c02174c28","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

