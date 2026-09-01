#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'PRESERVE_TASK_AUDIT = True' in t; p.write_text(t.replace('PRESERVE_TASK_AUDIT = True','PRESERVE_TASK_AUDIT = False'))
PY
