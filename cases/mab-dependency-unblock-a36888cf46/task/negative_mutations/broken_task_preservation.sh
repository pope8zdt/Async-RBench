#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'PRESERVE_RACE_HISTORY = True' in t; p.write_text(t.replace('PRESERVE_RACE_HISTORY = True','PRESERVE_RACE_HISTORY = False'))
PY
