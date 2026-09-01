#!/bin/bash
set -euo pipefail
cd /testbed
python3 - <<'PY'
from pathlib import Path
p=Path('lib/ansible/module_utils/basic.py'); s=p.read_text(); old='new_key = _remove_values_conditions(old_key, no_log_strings, None)'; new='new_key = old_key'
if old not in s: raise SystemExit('locked mutation anchor missing')
p.write_text(s.replace(old,new,1))
PY
