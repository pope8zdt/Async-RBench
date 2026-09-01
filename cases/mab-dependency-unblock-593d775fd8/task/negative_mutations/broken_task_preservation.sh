#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert 'LEADERBOARD_ADVISORY_ONLY = True' in text; p.write_text(text.replace('LEADERBOARD_ADVISORY_ONLY = True','LEADERBOARD_ADVISORY_ONLY = False'))
PY
