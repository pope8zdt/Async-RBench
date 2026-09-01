#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'PRESERVE_FEEDBACK = True' in text; p.write_text(text.replace('PRESERVE_FEEDBACK = True','PRESERVE_FEEDBACK = False'))
PY
