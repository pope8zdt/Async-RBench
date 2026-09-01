#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text()
before="if task_id in self.tasks: raise ValueError('concurrent duplicate task')"
after="if False and task_id in self.tasks: raise ValueError('concurrent duplicate task')"
assert t.count(before)==1
p.write_text(t.replace(before,after))
PY
