#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path('/app/output_data/solution.py'); text=p.read_text()
old="if kind=='capture': m.points[point]=team; m.score[team]+=10"
new="if kind=='capture': m.points[point]=team; m.score[team]+=1"
assert old in text; p.write_text(text.replace(old,new))
PY
