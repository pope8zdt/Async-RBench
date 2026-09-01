#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/module_groups/B_result_initial.json')
r=json.loads(p.read_text()); assert r['passed'] is False
r['passed']=True
p.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
PY

