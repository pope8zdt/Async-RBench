#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/database-diagnosis.sh
printf '%s
' '{"status":"provisional_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s
' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
