#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path('/app/output_data/solution.py'); text=p.read_text()
old='uid=hashlib.sha256(f"{provider}:{task_id}:{t.deadline.isoformat()}".encode()).hexdigest()'
new='uid=hashlib.sha256(f"{task_id}:{t.deadline.isoformat()}".encode()).hexdigest()'
assert old in text; p.write_text(text.replace(old,new))
PY
