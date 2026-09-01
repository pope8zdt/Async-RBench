#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json, pathlib
p = pathlib.Path('/app/output_data/font_size_result.json')
r = json.loads(p.read_text())
r['default_font_size'] = 16
p.write_text(json.dumps(r))
PY
