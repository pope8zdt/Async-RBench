#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s["right_wall_rotation_safe"]=False;s["rotation_reverts_or_kicks_on_collision"]=False;s["official_test_passed"]=False;p.write_text(json.dumps(r)+'\n')
PY

