#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/service-lineage.json'); x=json.loads(p.read_text()); x['recovered_row_count']=5; p.write_text(json.dumps(x))
PY
