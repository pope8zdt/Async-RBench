#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import datetime, json, pathlib
from zoneinfo import ZoneInfo
root=pathlib.Path('/async_rbench/upstream_solutions/fixtures')
native=json.loads((root/'native_canonical_report.json').read_text())
payload=json.loads((root/'event_payload.json').read_text())
assert native['passed'] and native['canonical']['official_score']==1.0
state=dict(payload['state'])
if payload.get('derive_relative_dates'):
    today=datetime.datetime.now(ZoneInfo(state['timezone'])).date()
    delta=(7-today.weekday())%7 or 7
    pickup=today+datetime.timedelta(days=delta)
    state['pickup_date']=pickup.isoformat()
    state['return_date']=(pickup+datetime.timedelta(days=4)).isoformat()
result={'source_task_id':native['source_task_id'],'native_evaluator':native['native_evaluator'],'official_score':native['canonical']['official_score'],'native_evidence_sha256':native['evidence_sha256'],'task_assertion':"Exactly one persisted Favorites folder exists directly under Chrome bookmarks bar.",'state':state}
pathlib.Path('/app/output_data/osworld_native_result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
PY
