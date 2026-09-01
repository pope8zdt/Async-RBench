#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'TRANSITIVE_READINESS = True' in text; p.write_text(text.replace('TRANSITIVE_READINESS = True','TRANSITIVE_READINESS = False'))
PY
