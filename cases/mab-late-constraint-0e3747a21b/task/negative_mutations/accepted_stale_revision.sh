#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/agreement.json'); a=json.loads(p.read_text()); a['accepted_revision']=1; a['price_usd']=16.98; p.write_text(json.dumps(a))
PY
