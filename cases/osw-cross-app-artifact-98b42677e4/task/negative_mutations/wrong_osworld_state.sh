#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());state=r['state']
state["embedded_image_index"]=2
state["embedded_image_sha256"]="d5bfc6194ab0ff2f1be9ea5465ca2681f2bb9e0207bbe5286ed837c956418dca"
p.write_text(json.dumps(r))
PY

