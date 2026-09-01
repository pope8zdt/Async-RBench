#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/dblp_bibtex_osworld.sh
printf '%s\n' '{"status":"cross_app_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:df67aebb-fb3a-44fd-b75b-51b6012df509","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

