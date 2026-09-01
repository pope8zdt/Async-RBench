#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text()
before="b['members'].get(user_id) not in {'owner','edit'}"
after="b['members'].get(user_id) not in {'owner','edit','view'}"
assert t.count(before)==1
p.write_text(t.replace(before,after))
PY
