#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/secret_path_clipboard_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:716a6079-22da-47f1-ba73-c9d58f986a38","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
