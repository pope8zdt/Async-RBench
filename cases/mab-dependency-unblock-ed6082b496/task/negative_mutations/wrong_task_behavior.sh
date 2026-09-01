#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'ENFORCE_MODULE_DEPENDENCIES = True' in t; p.write_text(t.replace('ENFORCE_MODULE_DEPENDENCIES = True','ENFORCE_MODULE_DEPENDENCIES = False'))
PY
