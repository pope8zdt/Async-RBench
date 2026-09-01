#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json, pathlib
p=pathlib.Path('/app/output_data/extension_installation.json'); r=json.loads(p.read_text())
r['loaded_unpacked']=False; r['load_error']='manifest not loaded'; p.write_text(json.dumps(r))
PY
