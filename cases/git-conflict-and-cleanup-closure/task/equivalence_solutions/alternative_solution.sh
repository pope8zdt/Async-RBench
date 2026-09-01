#!/usr/bin/env bash
set -euo pipefail
cd /app/repo
python3 /app/task_file/scripts/scan_refs.py || true
python3 /app/task_file/scripts/scan_packs.py || true
python3 /app/task_file/scripts/scan_objects.py
python3 /app/task_file/scripts/recover_secret.py --report /app/output_data/scan_reports/object_db.json
git gc --prune=now --aggressive
python3 /app/task_file/scripts/record_cleanup.py --attempt 1 --command 'git gc --prune=now --aggressive'
python3 /app/task_file/scripts/verify_closure.py || true
git reflog expire --expire=now --all
git gc --prune=now --aggressive
python3 /app/task_file/scripts/record_cleanup.py --attempt 2 --command 'git reflog expire --expire=now --all; git gc --prune=now --aggressive'
python3 /app/task_file/scripts/verify_closure.py
python3 /app/task_file/scripts/write_manifest.py
