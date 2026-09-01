#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'VALIDATE_SESSIONS = True' in text; p.write_text(text.replace('VALIDATE_SESSIONS = True','VALIDATE_SESSIONS = False'))
PY
