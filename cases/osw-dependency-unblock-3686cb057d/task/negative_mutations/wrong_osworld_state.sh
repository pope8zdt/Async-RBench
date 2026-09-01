#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());state=r['state']
state["gold_workbook_sha256"]="0"*64
p.write_text(json.dumps(r)+'\n')
PY
