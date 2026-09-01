#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'TREND_RANKING = True' in text; p.write_text(text.replace('TREND_RANKING = True','TREND_RANKING = False'))
PY
