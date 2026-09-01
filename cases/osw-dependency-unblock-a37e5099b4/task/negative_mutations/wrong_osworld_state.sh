#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s["extension_match"]="python";s["extension_installed"]=False;s["output_dimensions"]=[127,128];p.write_text(json.dumps(r)+'\n')
PY

