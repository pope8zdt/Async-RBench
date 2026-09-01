#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/terminal_focus_keybinding_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:vs_code:930fdb3b-11a8-46fe-9bac-577332e2640e","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
