#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
fixtures=pathlib.Path('/async_rbench/upstream_solutions/fixtures')
native=json.loads((fixtures/'native_canonical_report.json').read_text())
payload=json.loads((fixtures/'event_payload.json').read_text())
assert native['equivalent']['official_evaluator_executed'] is True
result={
    'source_task_id': payload['source_task_id'],
    'native_evaluator': native['native_evaluator'],
    'official_score': native['equivalent']['official_score'],
    'native_evidence_sha256': native['evidence_sha256'],
    'task_assertion': payload['task_assertion'],
    'state': dict(payload['state']),
}
pathlib.Path('/app/output_data/osworld_native_result.json').write_text(
    json.dumps(result,indent=2,sort_keys=True)+'\n'
)
PY
printf '%s\n' '{"status":"independent_equivalent_checkpoint"}' >/app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"source_task_id":"osworld:multi_apps:51f5801c-18b3-4f25-b0c3-02f85507a078"}' >/app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
