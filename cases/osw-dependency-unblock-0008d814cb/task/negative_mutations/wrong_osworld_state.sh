#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json')
r=json.loads(p.read_text())
state=r['state']
state["topic_title"]="Wrong topic"; state["topic_url"]="https://discussions.flightaware.com/c/general/5"; state["active_tab_url"]=state["topic_url"]
p.write_text(json.dumps(r))
PY
