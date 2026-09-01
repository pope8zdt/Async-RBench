#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
p='/app/output_data/event_monitor_report.json'; d=json.load(open(p)); d['stream_revision']='0'*64; json.dump(d,open(p,'w'),indent=2)
PY
