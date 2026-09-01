#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'ENFORCE_AVAILABILITY = True' in text; p.write_text(text.replace('ENFORCE_AVAILABILITY = True','ENFORCE_AVAILABILITY = False'))
PY
