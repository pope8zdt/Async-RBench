#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/recovered.json'); rows=json.loads(p.read_text()); p.write_text(json.dumps(rows[:5]))
q=Path('/app/service_seed.json'); s=json.loads(q.read_text()); s={k:v for k,v in s.items() if not k.startswith('item:') or k.endswith('apple')}; q.write_text(json.dumps(s))
PY
