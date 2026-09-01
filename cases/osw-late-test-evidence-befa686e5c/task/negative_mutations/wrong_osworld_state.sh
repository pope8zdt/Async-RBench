#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s['initial_spawn_grid_aligned']=False;s['respawn_grid_aligned']=False;s['snake_reaches_food']=False;s['official_test_passed']=False;p.write_text(json.dumps(r)+'\n')
PY
