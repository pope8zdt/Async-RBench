#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path('/app/output_data/solution.py'); text=p.read_text()
old="if u not in r.reviewers or expected_version!=r.version: raise RuntimeError('version conflict')"
new="if u not in r.reviewers: raise RuntimeError('version conflict')"
assert old in text; p.write_text(text.replace(old,new))
PY
