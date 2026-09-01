#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'EXCLUDE_NONEXECUTABLE = True' in text; p.write_text(text.replace('EXCLUDE_NONEXECUTABLE = True','EXCLUDE_NONEXECUTABLE = False'))
PY
