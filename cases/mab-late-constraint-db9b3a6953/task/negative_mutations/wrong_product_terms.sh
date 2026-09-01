#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/agreement.json');d=json.loads(p.read_text());d['terms']={};p.write_text(json.dumps(d))
PY
