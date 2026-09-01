#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
p='/app/output_data/closure_report.json'; d=json.load(open(p)); d['closed']=False; d['checks']['all_objects_clean']=False; json.dump(d,open(p,'w'),indent=2)
PY
