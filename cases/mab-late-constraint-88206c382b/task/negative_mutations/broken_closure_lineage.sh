#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/negotiation_closure.json'); d=json.loads(p.read_text()); d['event_receipt_sha256']='0'*64; p.write_text(json.dumps(d))
PY
