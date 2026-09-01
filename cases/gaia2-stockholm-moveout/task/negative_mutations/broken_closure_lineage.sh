#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
p='/app/output_data/saved_list_final.json'; d=json.load(open(p)); d['saved']=d['saved'][:-1]; json.dump(d,open(p,'w'),indent=2)
PY
