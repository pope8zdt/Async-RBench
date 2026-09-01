#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/event_receipt.json'); r=json.loads(p.read_text()); r['case_id']='wrong-case'; p.write_text(json.dumps(r))
PY
