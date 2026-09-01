#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); old="needed=(t['duration']+29)//30"; assert old in t; p.write_text(t.replace(old,"needed=1"))
PY
