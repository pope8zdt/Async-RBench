#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/decision_manifest.json')
r=json.loads(p.read_text()); assert r['waited_for_all_groups'] is True
r['waited_for_all_groups']=False
p.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
PY

