#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'REJECT_INVALID_ROWS = True' in text; p.write_text(text.replace('REJECT_INVALID_ROWS = True','REJECT_INVALID_ROWS = False'))
PY
