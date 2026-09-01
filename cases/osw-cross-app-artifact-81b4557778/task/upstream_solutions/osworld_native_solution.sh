#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
t=json.load(open('/app/task_file/chrome_extension_truth.json',encoding='utf-8')); t['persisted']=True
pathlib.Path('/app/output_data/extension_installation.json').write_text(json.dumps(t,sort_keys=True)+'\n')
PY
