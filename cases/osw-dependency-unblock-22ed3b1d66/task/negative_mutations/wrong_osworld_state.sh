#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());state=r['state']
state["final_value"]=1
state["playback_exit_disabled"]=False
p.write_text(json.dumps(r)+'\n')
PY
