#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'CONVERT_CURRENCIES = True' in text; p.write_text(text.replace('CONVERT_CURRENCIES = True','CONVERT_CURRENCIES = False'))
PY
