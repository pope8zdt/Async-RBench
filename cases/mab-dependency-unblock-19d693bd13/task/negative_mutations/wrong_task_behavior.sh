#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'DERIVE_HEALTH = True' in text; p.write_text(text.replace('DERIVE_HEALTH = True','DERIVE_HEALTH = False'))
PY
