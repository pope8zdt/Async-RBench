#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s['sample_count']=29;s['official_line_count']=30;s['line_count_check_passed']=False;p.write_text(json.dumps(r)+'\n')
PY
