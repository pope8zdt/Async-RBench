#!/bin/bash
set -euo pipefail
cd /testbed
python3 - <<'PY'
from pathlib import Path
p=Path('packages/svelte/src/utils.js')
text=p.read_text(encoding="utf-8")
old="\t'inert',"
if old not in text:
    raise SystemExit(f"task-specific mutation anchor missing in {p}")
p.write_text(text.replace(old, '\t/* inert deliberately removed by negative variant */', 1), encoding="utf-8")
PY
