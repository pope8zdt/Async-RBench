#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path('/app/output_data/solution.py'); text=p.read_text(); old='PRESERVE_TEAM_WORKSPACE = True'; new='PRESERVE_TEAM_WORKSPACE = False'; assert old in text; p.write_text(text.replace(old,new,1))
PY
