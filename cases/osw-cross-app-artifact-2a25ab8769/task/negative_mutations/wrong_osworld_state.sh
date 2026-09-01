#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/osworld_native_result.json');r=json.loads(p.read_text());s=r['state'];s["tracks"][0]["title"]="Missing";s["tracks"].pop();s["track_count"]=4;s["all_audio_preserved"]=False;p.write_text(json.dumps(r)+'\n')
PY

