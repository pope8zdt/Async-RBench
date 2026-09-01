#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
r=pathlib.Path('/async_rbench/upstream_solutions/fixtures');n=json.loads((r/'native_canonical_report.json').read_text());p=json.loads((r/'event_payload.json').read_text());assert n['passed'] and n['canonical']['official_score']==1
q={'source_task_id':n['source_task_id'],'native_evaluator':n['native_evaluator'],'official_score':n['canonical']['official_score'],'native_evidence_sha256':n['evidence_sha256'],'task_assertion':p['task_assertion'],'state':p['state']};pathlib.Path('/app/output_data/osworld_native_result.json').write_text(json.dumps(q,indent=2,sort_keys=True)+'\n')
PY

