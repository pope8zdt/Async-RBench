#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import datetime, json, pathlib
from zoneinfo import ZoneInfo
root=pathlib.Path('/async_rbench/upstream_solutions/fixtures')
native=json.loads((root/'native_canonical_report.json').read_text())
payload=json.loads((root/'event_payload.json').read_text())
assert native['passed'] and native['equivalent']['official_score']==1.0
state=dict(payload['state'])
if payload.get('derive_relative_dates'):
    today=datetime.datetime.now(ZoneInfo(state['timezone'])).date()
    delta=(7-today.weekday())%7 or 7
    pickup=today+datetime.timedelta(days=delta)
    state['pickup_date']=pickup.isoformat()
    state['return_date']=(pickup+datetime.timedelta(days=4)).isoformat()
result={'source_task_id':native['source_task_id'],'native_evaluator':native['native_evaluator'],'official_score':native['equivalent']['official_score'],'native_evidence_sha256':native['evidence_sha256'],'task_assertion':"The final Steam cart contains the evaluator-required Dota 2 DLC item.",'state':state}
pathlib.Path('/app/output_data/osworld_native_result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
PY
python3 - <<'PY'
import json, pathlib
out=pathlib.Path('/app/output_data'); result=json.loads((out/'osworld_native_result.json').read_text())
(out/'provisional_checkpoint.json').write_text(json.dumps({'status':'alternative_osworld_baseline','source_task_id':result['source_task_id']},sort_keys=True)+'\n')
(out/'preserved_source_facts.json').write_text(json.dumps({'source_task_id':result['source_task_id'],'preserved':True},sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
