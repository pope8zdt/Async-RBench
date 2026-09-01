#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'STRUCTURED_BALANCE = True' in text; p.write_text(text.replace('STRUCTURED_BALANCE = True','STRUCTURED_BALANCE = False'))
PY
