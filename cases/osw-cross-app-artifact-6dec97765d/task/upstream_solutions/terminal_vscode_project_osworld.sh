#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
f=pathlib.Path('/async_rbench/upstream_solutions/fixtures');n=json.loads((f/'native_canonical_report.json').read_text());p=json.loads((f/'event_payload.json').read_text());o=pathlib.Path('/app/output_data');r={'source_task_id':p['source_task_id'],'native_evaluator':n['native_evaluator'],'official_score':n['canonical']['official_score'],'native_evidence_sha256':n['evidence_sha256'],'task_assertion':p['task_assertion'],'state':p['state']};(o/'osworld_native_result.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
PY
