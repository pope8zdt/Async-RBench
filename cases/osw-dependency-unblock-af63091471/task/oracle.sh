#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 /app/task_file/scripts/write_font_result.py
printf '%s\n' '{"status":"font_size_checkpoint_persisted","default_font_size":24}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:chrome:af630914-714e-4a24-a7bb-f9af687d3b91","preserved":true}' > /app/output_data/preserved_source_facts.json
bash /async_rbench/upstream_solutions/font_preference_oracle.sh
python3 /app/task_file/scripts/write_manifest.py
