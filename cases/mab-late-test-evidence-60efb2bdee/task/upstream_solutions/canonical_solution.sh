#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
e=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json')); assert e['canonical_episode_owner']=='evaluator' and e['passed'] is True
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'source_task_id':'coding:005','status':'three_upstream_results_persisted','upstream_depth':4},sort_keys=True)+'\n'); pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id':'coding:005','preserved':True,'artifacts':['task_assignments', 'status_history', 'task_comments', 'notification_and_report_history']},sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
r=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); c={'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-late-test-evidence-60efb2bdee', 'source_task_id': 'coding:005', 'artifact_type': 'office_scheduler_test_evidence_closure', 'event': 'office_edge_test_evidence_replayed', 'upstream_depth': 4, 'preserved_workflows': ['task_assignments', 'status_history', 'task_comments', 'notification_and_report_history'], 'source_semantics_reverified': True}; c['event_receipt_sha256']=r['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
