#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'APPLY_REALTIME_SNAPSHOT = True' in text; p.write_text(text.replace('APPLY_REALTIME_SNAPSHOT = True','APPLY_REALTIME_SNAPSHOT = False'))
PY
