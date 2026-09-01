#!/usr/bin/env bash
set -euo pipefail
# Benchmark-maintenance oracle: produce the correct saved list, the notification
# record, the event-monitor report and the decision manifest under the output
# root. Deterministic and mode-invariant: execution mode changes only control
# flow, never the container's correct final state or this script.
/bin/bash /async_rbench/upstream_solutions/reference_solution.sh
python3 /app/task_file/scripts/write_manifest.py
