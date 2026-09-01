#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'PRESERVE_ROOM_HISTORY = True' in text; p.write_text(text.replace('PRESERVE_ROOM_HISTORY = True','PRESERVE_ROOM_HISTORY = False'))
PY
