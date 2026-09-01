#!/bin/bash
set -euo pipefail
cd /testbed
python3 - <<'PY'
from pathlib import Path
p=Path('src/builder/command.rs')
text=p.read_text(encoding="utf-8")
old='*current_disp_ord = current + 1;'
if old not in text:
    raise SystemExit(f"task-specific mutation anchor missing in {p}")
p.write_text(text.replace(old, '*current_disp_ord = current;', 1), encoding="utf-8")
PY
