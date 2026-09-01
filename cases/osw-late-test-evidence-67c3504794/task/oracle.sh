#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/speedtest_results_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:26660ad1-6ebb-4f59-8cba-a8432dfe8d38","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py

