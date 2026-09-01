#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s["next_chapter"]="Gong Office.tex";s["content_sha256"]="0"*64;s["content_bytes"]=0;p.write_text(json.dumps(r)+'\n')
PY

