#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/gemini_docx_osworld.sh
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:5bc63fb9-276a-4439-a7c1-9dc76401737f","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

