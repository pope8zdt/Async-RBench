#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'USE_RETURNED_RESEARCH_AUTHORITY = True' in t; p.write_text(t.replace('USE_RETURNED_RESEARCH_AUTHORITY = True','USE_RETURNED_RESEARCH_AUTHORITY = False'))
PY
