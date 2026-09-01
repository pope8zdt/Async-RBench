#!/bin/bash
set -euo pipefail
cd /testbed
python3 - <<'PY'
from pathlib import Path
p=Path('lib/ansible/module_utils/urls.py'); s=p.read_text(); old="if decompress and r.headers.get('content-encoding', '').lower() == 'gzip':"; new="if False and decompress and r.headers.get('content-encoding', '').lower() == 'gzip':"
if old not in s: raise SystemExit('locked mutation anchor missing')
p.write_text(s.replace(old,new,1))
PY
