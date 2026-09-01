#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/deployment.json'); x=json.loads(p.read_text()); x['backend']='tensor'; x['world_size']=4; p.write_text(json.dumps(x))
PY

