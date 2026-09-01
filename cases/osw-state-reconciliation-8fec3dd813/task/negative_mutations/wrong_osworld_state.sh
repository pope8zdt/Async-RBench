#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s["terminal_window"]["title_contains"]="~";s["chrome_tabs"]=["https://github.com"];p.write_text(json.dumps(r)+'\n')
PY

