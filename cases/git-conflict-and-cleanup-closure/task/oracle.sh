#!/usr/bin/env bash
set -uo pipefail
# Benchmark-maintenance oracle: reproduce the complete correct process.
# The naive gc attempt genuinely leaves the secret packed (the reset-away
# dangling commit survives because the HEAD reflog still references it), so the
# closure verifier reports closed=false and the cleanup must be re-delegated
# with reflog expiry. This is the exact async-dynamic-replanning behaviour the
# case measures, and it is deterministic.
cd /app/repo
python3 /app/task_file/scripts/scan_refs.py   || true   # found=false -> exit 1
python3 /app/task_file/scripts/scan_packs.py  || true   # found=false -> exit 1
python3 /app/task_file/scripts/scan_objects.py          # found=true  -> exit 0
python3 /app/task_file/scripts/recover_secret.py --report /app/output_data/scan_reports/object_db.json
git gc --prune=now --aggressive
python3 /app/task_file/scripts/record_cleanup.py --attempt 1 --command "git gc --prune=now --aggressive"
python3 /app/task_file/scripts/verify_closure.py || true # closed=false -> exit 1
git reflog expire --expire=now --all
git gc --prune=now --aggressive
python3 /app/task_file/scripts/record_cleanup.py --attempt 2 --command "git reflog expire --expire=now --all; git gc --prune=now --aggressive"
python3 /app/task_file/scripts/verify_closure.py          # closed=true  -> exit 0
python3 /app/task_file/scripts/write_manifest.py
