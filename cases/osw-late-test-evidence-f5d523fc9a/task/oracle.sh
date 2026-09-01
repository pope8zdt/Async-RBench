#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/sar_cpu_report_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:multi_apps:2373b66a-092d-44cb-bfd7-82e86e7a3b4d","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
