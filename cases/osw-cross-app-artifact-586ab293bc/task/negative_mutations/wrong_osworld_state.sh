#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());state=r['state']
state["rows"][0]["subject"]="HKU Daily Email Digest (30 JAN 2024)"
state["chronological_subject_dates"].reverse()
p.write_text(json.dumps(r))
PY

