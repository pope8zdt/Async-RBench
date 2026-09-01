#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s['target_layer_height']=511;s['aspect_ratio_preserved']=False;s['structure_similarity_passed']=False;p.write_text(json.dumps(r)+'\n')
PY
