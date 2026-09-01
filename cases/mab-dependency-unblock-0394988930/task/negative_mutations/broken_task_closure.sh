#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/decision_manifest.json'); d=json.loads(p.read_text()); d['source_semantics_reverified']=False; p.write_text(json.dumps(d,sort_keys=True)+'\n')
PY
