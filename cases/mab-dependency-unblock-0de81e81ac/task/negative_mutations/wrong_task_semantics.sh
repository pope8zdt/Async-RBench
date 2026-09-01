#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'TRAFFIC_AWARE = True' in text; p.write_text(text.replace('TRAFFIC_AWARE = True','TRAFFIC_AWARE = False'))
PY
