#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/database_diagnosis.json'); d=json.loads(p.read_text()); d['selected_causes']=d['superseded_causes']; p.write_text(json.dumps(d))
PY
