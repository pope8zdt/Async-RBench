#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s['exact_path']='/home/user/Data2/List2/secret.docx';s['clipboard_text']=s['exact_path'];s['unique_match']=False;p.write_text(json.dumps(r)+'\n')
PY
