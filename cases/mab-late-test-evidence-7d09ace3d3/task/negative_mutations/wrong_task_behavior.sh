#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'DEDUPLICATE_EDGE_EVIDENCE = True' in t; p.write_text(t.replace('DEDUPLICATE_EDGE_EVIDENCE = True','DEDUPLICATE_EDGE_EVIDENCE = False'))
PY
