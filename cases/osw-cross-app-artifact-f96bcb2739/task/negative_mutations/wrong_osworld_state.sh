#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s['imputation_mean']=0;s['median_after_imputation']=0;s['result_text']='0';s['only_numeric']=False;p.write_text(json.dumps(r)+'\n')
PY
