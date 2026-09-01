#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/sentence_spacing_osworld.sh
printf '%s\n' '{"status":"task_specific_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:libreoffice_writer:88fe4b2d-3040-4c70-9a70-546a47764b48","preserved":true}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
