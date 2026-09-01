#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path('/app/output_data/solution.py'); text=p.read_text(); old="EVENT_SCHEMA='holistic_wellness_dependency_v2'"; new="EVENT_SCHEMA='foreign_event_contract'"; assert old in text; p.write_text(text.replace(old,new,1))
PY
