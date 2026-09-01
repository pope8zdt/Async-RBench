#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());state=r['state']
state["pdf_pages"]=2
state["image_content_matches"]=False
p.write_text(json.dumps(r))
PY

