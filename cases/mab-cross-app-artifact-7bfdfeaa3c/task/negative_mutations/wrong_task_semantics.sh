#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); text=p.read_text(); assert "TRACK_ORDER_POLICY = 'track_then_tick'" in text; p.write_text(text.replace("TRACK_ORDER_POLICY = 'track_then_tick'","TRACK_ORDER_POLICY = 'arrival_order'"))
PY
