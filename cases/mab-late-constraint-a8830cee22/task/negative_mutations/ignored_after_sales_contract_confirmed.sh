#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/negotiation_closure.json'); d=json.loads(p.read_text()); d['authority_applied']=False; p.write_text(json.dumps(d))
PY
