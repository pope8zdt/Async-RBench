#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'PRESERVE_SCHEDULE_HISTORY = True' in t; p.write_text(t.replace('PRESERVE_SCHEDULE_HISTORY = True','PRESERVE_SCHEDULE_HISTORY = False'))
PY
