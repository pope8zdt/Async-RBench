#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/event_receipt.json');d=json.loads(p.read_text());d['source_task_id']='foreign';p.write_text(json.dumps(d))
PY
