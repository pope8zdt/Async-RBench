#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/vscode_keybinding_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:vs_code:ea98c5d7-3cf9-4f9b-8ad3-366b58e0fcae","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
