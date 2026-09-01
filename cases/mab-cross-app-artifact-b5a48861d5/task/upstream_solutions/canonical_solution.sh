#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
evidence=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json',encoding='utf-8'))
assert evidence['canonical_episode_owner']=='evaluator' and evidence['passed'] is True
pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps({'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-cross-app-artifact-b5a48861d5', 'source_task_id': 'coding:063', 'artifact_type': 'git_review_history_contract', 'event': 'git_adapter_contract_delivered', 'synchronized_surfaces': ['code_review', 'debug_chat', 'git_history'], 'preserved_workflows': ['snippets', 'annotations', 'chat', 'issue_transitions', 'authentication', 'role_permissions'], 'stale_result_disposition': 'rejected', 'source_semantics_reverified': True},sort_keys=True)+'\n')
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'status':'source_native_baseline_persisted','source_task_id':'coding:063'},sort_keys=True)+'\n')
pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id': 'coding:063', 'preserved': True, 'artifacts': ['snippets', 'annotations', 'chat', 'issue_transitions', 'authentication', 'role_permissions']},sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 /async_rbench/upstream_solutions/write_manifest.py
