#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/period_rate_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:libreoffice_calc:21ab7b40-77c2-4ae6-8321-e00d3a086c73","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
