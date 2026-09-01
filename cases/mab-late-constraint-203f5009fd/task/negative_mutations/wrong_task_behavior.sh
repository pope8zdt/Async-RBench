#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'ENFORCE_RBAC = True' in t; p.write_text(t.replace('ENFORCE_RBAC = True','ENFORCE_RBAC = False'))
PY
