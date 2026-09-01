#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/agreement.json');d=json.loads(p.read_text());d['accepted_revision']=1;d['price_usd']=24.93;p.write_text(json.dumps(d))
PY
