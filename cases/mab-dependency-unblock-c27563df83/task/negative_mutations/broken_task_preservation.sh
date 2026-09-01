#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'PRESERVE_FINANCIAL_HISTORY = True' in t; p.write_text(t.replace('PRESERVE_FINANCIAL_HISTORY = True','PRESERVE_FINANCIAL_HISTORY = False'))
PY
