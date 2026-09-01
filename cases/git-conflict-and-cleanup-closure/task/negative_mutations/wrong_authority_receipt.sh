#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
p='/app/output_data/recovery_report.json'; d=json.load(open(p)); d['source_scan']='pack'; json.dump(d,open(p,'w'),indent=2)
PY
