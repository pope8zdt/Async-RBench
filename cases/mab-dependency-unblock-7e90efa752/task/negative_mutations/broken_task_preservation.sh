#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'PRESERVE_PERFORMANCE = True' in text; p.write_text(text.replace('PRESERVE_PERFORMANCE = True','PRESERVE_PERFORMANCE = False'))
PY
