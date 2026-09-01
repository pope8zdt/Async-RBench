#!/bin/bash
set -euo pipefail
cd /testbed
python3 - <<'PY'
from pathlib import Path
p=Path('src/output/help.rs'); s=p.read_text(); old='{author-with-newline}{about-with-newline}'; new='{author-section}{about-section}'
if old not in s: raise SystemExit('locked mutation anchor missing')
p.write_text(s.replace(old,new,1))
PY
