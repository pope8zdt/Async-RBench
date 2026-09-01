#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());state=r['state']
state["source_files"]=["1.txt","3.txt","2.txt","4.txt","5.txt"]
state["separator"]="\n"
p.write_text(json.dumps(r))
PY

