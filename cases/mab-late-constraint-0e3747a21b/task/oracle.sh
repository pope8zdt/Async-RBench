#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/negotiation-agreement.sh
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
