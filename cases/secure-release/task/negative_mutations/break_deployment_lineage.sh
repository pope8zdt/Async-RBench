#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/release-manifest.json')
d=json.loads(p.read_text())
d['deployed_main']='0'*40
p.write_text(json.dumps(d))
PY

