#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'APPLY_UNIQUE_EDGE_TESTS = True' in t; p.write_text(t.replace('APPLY_UNIQUE_EDGE_TESTS = True','APPLY_UNIQUE_EDGE_TESTS = False'))
PY
