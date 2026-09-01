#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'PRIORITY_FIRST = True' in text; p.write_text(text.replace('PRIORITY_FIRST = True','PRIORITY_FIRST = False'))
PY
