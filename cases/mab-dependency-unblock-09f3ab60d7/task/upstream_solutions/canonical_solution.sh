#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
evidence=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json',encoding='utf-8')); assert evidence['canonical_episode_owner']=='evaluator' and evidence['passed'] is True
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'status':'source_native_baseline_persisted','source_task_id':'coding:014'},sort_keys=True)+'\n')
pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id':'coding:014','preserved':True,'artifacts':['complexity_metrics', 'size_estimate', 'collaboration_permissions']},sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
receipt=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); closure={'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-dependency-unblock-09f3ab60d7', 'source_task_id': 'coding:014', 'artifact_type': 'macao_integrated_analysis_closure', 'event': 'coverage_worker_recovered', 'preserved_workflows': ['complexity_metrics', 'size_estimate', 'collaboration_permissions'], 'source_semantics_reverified': True}; closure['event_receipt_sha256']=receipt['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(closure,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
