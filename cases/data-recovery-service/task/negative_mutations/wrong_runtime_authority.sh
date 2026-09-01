#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/service_seed.json'); s=json.loads(p.read_text()); s.pop(next(k for k in s if k.startswith('item:')),None); p.write_text(json.dumps(s))
PY
