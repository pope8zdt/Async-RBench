#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/regression_result.json')
r=json.loads(p.read_text()); assert len(r['regression_revision'])==64
r['regression_revision']='0'*64
p.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
PY

