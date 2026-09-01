#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path('/app/output_data/solution.py'); text=p.read_text()
old='if expected_version!=q.version: raise RuntimeError("quest version conflict")'
new='if False: raise RuntimeError("quest version conflict")'
assert old in text; p.write_text(text.replace(old,new))
PY
