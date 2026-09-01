#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'PRESERVE_FIVE_QUESTION_STRUCTURE = True' in t; p.write_text(t.replace('PRESERVE_FIVE_QUESTION_STRUCTURE = True','PRESERVE_FIVE_QUESTION_STRUCTURE = False'))
PY
