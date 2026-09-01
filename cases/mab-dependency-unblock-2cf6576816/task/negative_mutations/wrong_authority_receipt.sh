#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/event_receipt.json'); d=json.loads(p.read_text()); d['authority']['contract']='single_order_v0'; p.write_text(json.dumps(d)+'\n')
PY
