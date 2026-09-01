#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/event_receipt.json'); d=json.loads(p.read_text()); d['authority']['contract']='foreign_contract'; p.write_text(json.dumps(d,sort_keys=True)+'\n')
PY
