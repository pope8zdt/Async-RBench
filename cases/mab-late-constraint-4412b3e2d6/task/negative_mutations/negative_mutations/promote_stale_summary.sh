#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/coding_closure.json');d=json.loads(p.read_text());d['qualified_result_consumed']=False;p.write_text(json.dumps(d))
PY
