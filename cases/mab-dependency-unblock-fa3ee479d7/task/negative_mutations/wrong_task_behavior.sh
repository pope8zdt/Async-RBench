#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'ENFORCE_GROUP_INTEGRITY = True' in t; p.write_text(t.replace('ENFORCE_GROUP_INTEGRITY = True','ENFORCE_GROUP_INTEGRITY = False'))
PY
