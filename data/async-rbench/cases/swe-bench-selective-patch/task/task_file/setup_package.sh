#!/usr/bin/env bash
# Build-time fixture builder for swe-bench-selective-patch.
#
# The trimmed sklearn package is already shipped in its buggy base state under
# /app/task_file/src/sklearn. This step records the base (buggy) revision of
# every source file into /app/task_file/src/BASE_MANIFEST.json so the verifier
# can later detect that a fix was applied and that the repair stayed selective
# (only the fix target changed). It also creates the output directory.
#
# The script is REMOVED from the image right after it runs (see Dockerfile), so
# no fixture-building material reaches the participant.
set -euo pipefail

PY=python

"$PY" - <<'PY'
import hashlib
import json
import os

root = "/app/task_file/src/sklearn"
manifest = {}
for dirpath, _dirnames, filenames in os.walk(root):
    for name in sorted(filenames):
        if not name.endswith(".py"):
            continue
        path = os.path.join(dirpath, name)
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        manifest[rel] = hashlib.sha256(open(path, "rb").read()).hexdigest()
out = "/app/task_file/src/BASE_MANIFEST.json"
with open(out, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
print("recorded %d base source revisions" % len(manifest))
PY

mkdir -p /app/output_data/module_groups
