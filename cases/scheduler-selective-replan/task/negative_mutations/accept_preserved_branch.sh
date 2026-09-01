#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/task_file/output_data/decision_manifest.json')
d=json.loads(p.read_text())
d['replanned_bucket']='bucket1'
p.write_text(json.dumps(d))
PY

