#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'ORDERED_EVENTS = True' in text; p.write_text(text.replace('ORDERED_EVENTS = True','ORDERED_EVENTS = False'))
PY
