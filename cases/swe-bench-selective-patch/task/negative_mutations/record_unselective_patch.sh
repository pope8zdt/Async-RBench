#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/decision_manifest.json')
r=json.loads(p.read_text()); changed=list(r['changed_files_final'])
assert 'utils/multiclass.py' in changed
r['changed_files_final']=changed+['metrics/_classification.py']
p.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
PY

