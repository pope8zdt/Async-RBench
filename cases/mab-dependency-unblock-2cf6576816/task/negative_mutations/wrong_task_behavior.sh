#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'PARTITION_BY_RESTAURANT = True' in text; p.write_text(text.replace('PARTITION_BY_RESTAURANT = True','PARTITION_BY_RESTAURANT = False'))
PY
