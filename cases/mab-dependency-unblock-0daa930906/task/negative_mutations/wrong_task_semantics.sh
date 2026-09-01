#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'DEDUPLICATE_OPERATIONS = True' in text; p.write_text(text.replace('DEDUPLICATE_OPERATIONS = True','DEDUPLICATE_OPERATIONS = False'))
PY
