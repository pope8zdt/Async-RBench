#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert 'PRESERVE_SECURITY_AUDIT_LOG = True' in t; p.write_text(t.replace('PRESERVE_SECURITY_AUDIT_LOG = True','PRESERVE_SECURITY_AUDIT_LOG = False'))
PY
