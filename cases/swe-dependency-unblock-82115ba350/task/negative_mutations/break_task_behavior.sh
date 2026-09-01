#!/bin/bash
set -euo pipefail
cd /testbed
python3 - <<'PY'
from pathlib import Path
p=Path('sympy/matrices/expressions/matexpr.py')
text=p.read_text(encoding="utf-8")
old='return KroneckerDelta(i, j)'
if old not in text:
    raise SystemExit(f"task-specific mutation anchor missing in {p}")
p.write_text(text.replace(old, 'return S.Zero', 1), encoding="utf-8")
PY
