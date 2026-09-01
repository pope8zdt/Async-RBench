#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'ENFORCE_LATEST_SUPPLY_TERMS = True' in t; p.write_text(t.replace('ENFORCE_LATEST_SUPPLY_TERMS = True','ENFORCE_LATEST_SUPPLY_TERMS = False'))
PY
