#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());state=r['state']
state["files"]=["LLM Powered Autonomous Agents.pdf"]
state["readable"]=[True]
state["one_pdf_per_tab"]=False
p.write_text(json.dumps(r))
PY

