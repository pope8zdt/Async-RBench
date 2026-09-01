#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'USE_DERIVED_F_DIVERGENCE_AUTHORITY = True' in t; p.write_text(t.replace('USE_DERIVED_F_DIVERGENCE_AUTHORITY = True','USE_DERIVED_F_DIVERGENCE_AUTHORITY = False'))
PY
