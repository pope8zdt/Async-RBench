#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'VERSION_ISOLATION = True' in text; p.write_text(text.replace('VERSION_ISOLATION = True','VERSION_ISOLATION = False'))
PY
