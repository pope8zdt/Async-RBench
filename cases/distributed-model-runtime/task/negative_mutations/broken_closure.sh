#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/batch-lineage.json'); x=json.loads(p.read_text()); x['profile_version']='v1'; p.write_text(json.dumps(x))
PY

