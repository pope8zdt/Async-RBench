#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'PRESERVE_COLLABORATION = True' in text; p.write_text(text.replace('PRESERVE_COLLABORATION = True','PRESERVE_COLLABORATION = False'))
PY
