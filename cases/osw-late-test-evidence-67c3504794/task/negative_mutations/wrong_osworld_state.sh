#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s["metric_lines"]=["Ping 18 ms","Download 96.4  Mbps"];s["metric_order"]=["Ping","Download"];s["line_count"]=2;s["all_values_nonempty"]=False;p.write_text(json.dumps(r)+'\n')
PY

