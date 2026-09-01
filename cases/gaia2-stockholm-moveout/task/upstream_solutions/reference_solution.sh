#!/usr/bin/env bash
set -euo pipefail
# Benchmark-maintenance oracle entry point (injected, never shipped to the
# participant image). Runs the deterministic reference solution against the
# public task material and writes the correct deliverables under /app/output_data.
exec python3 /async_rbench/upstream_solutions/reference_solution.py \
  --task-root /app/task_file \
  --output-root /app/output_data
