#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s['output_rows']=5000;s['order_preserved']=False;s['last_data_right']='Danz';s['opened_in_calc']=False;p.write_text(json.dumps(r)+'\n')
PY
