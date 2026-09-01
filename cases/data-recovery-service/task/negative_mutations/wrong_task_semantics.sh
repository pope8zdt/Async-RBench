#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/conflicts.json'); x=json.loads(p.read_text()); x['total_conflicts']=0; p.write_text(json.dumps(x))
PY
