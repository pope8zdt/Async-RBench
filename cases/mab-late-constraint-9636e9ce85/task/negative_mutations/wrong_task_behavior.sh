#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'ENFORCE_DEPENDENCY_POLICY = True' in t; p.write_text(t.replace('ENFORCE_DEPENDENCY_POLICY = True','ENFORCE_DEPENDENCY_POLICY = False'))
PY
