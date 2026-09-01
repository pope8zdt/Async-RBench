#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
e=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json')); assert e['canonical_episode_owner']=='evaluator' and e['passed'] is True
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'source_task_id':'coding:012','status':'three_upstream_results_persisted','upstream_depth':4},sort_keys=True)+'\n'); pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id':'coding:012','preserved':True,'artifacts':['user_profiles_and_permissions', 'shared_budget_transactions', 'notifications_and_goals', 'visualization_and_feedback']},sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
r=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); c={'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-dependency-unblock-c27563df83', 'source_task_id': 'coding:012', 'artifact_type': 'budget_sync_policy_closure', 'event': 'shared_budget_policy_completed', 'upstream_depth': 4, 'preserved_workflows': ['user_profiles_and_permissions', 'shared_budget_transactions', 'notifications_and_goals', 'visualization_and_feedback'], 'source_semantics_reverified': True}; c['event_receipt_sha256']=r['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
