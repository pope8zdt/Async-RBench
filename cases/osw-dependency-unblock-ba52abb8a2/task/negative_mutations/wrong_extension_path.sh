#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/extension_result.json'); r=json.loads(p.read_text()); r['extracted_path']='/home/user/Desktop/helloExtension.zip'; p.write_text(json.dumps(r))
PY
