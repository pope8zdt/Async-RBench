#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json, pathlib
p=pathlib.Path('/app/output_data/presentation_audio.json'); r=json.loads(p.read_text())
r['audio_role']='visible media object'; r['continue_across_slides']=False; p.write_text(json.dumps(r))
PY
