#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/app/task_file/output_data/plan_b1.jsonl'); rows=[json.loads(x) for x in p.read_text().splitlines()]; rows[0]['shape']['seq_align']=1; p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
PY

