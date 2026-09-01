#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s['project_path']='/home/user/Desktop';s['project_basename']='Desktop';s['open_project_probe']='Desktop';s['official_config_check_passed']=False;p.write_text(json.dumps(r)+'\n')
PY
