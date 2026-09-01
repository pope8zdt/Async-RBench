#!/bin/bash
set -euo pipefail
cd /testbed
python3 - <<'PY'
from pathlib import Path
p=Path('lib/ansible/module_utils/facts/sysctl.py'); s=p.read_text()
old="module.warn('Unable to read sysctl: %s' % to_text(e))"
new="module.warn('mutated sysctl command failure: %s' % to_text(e))"
if old not in s: raise SystemExit('locked mutation anchor missing')
p.write_text(s.replace(old,new,1))
PY
