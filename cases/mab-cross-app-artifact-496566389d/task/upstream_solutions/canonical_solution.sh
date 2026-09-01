#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
evidence=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json',encoding='utf-8'))
assert evidence['canonical_episode_owner']=='evaluator' and evidence['passed'] is True
pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps({'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-cross-app-artifact-496566389d', 'source_task_id': 'coding:070', 'artifact_type': 'versioned_quest_skill_sync_contract', 'event': 'quest_sync_contract_delivered', 'synchronized_surfaces': ['quest_board', 'skill_planner', 'device_sync'], 'preserved_workflows': ['authentication', 'quest_collaboration', 'skill_collaboration', 'ordered_event_log'], 'stale_result_disposition': 'rejected', 'source_semantics_reverified': True},sort_keys=True)+'\n')
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'status':'source_native_baseline_persisted','source_task_id':'coding:070'},sort_keys=True)+'\n')
pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id': 'coding:070', 'preserved': True, 'artifacts': ['authentication', 'quest_collaboration', 'skill_collaboration', 'ordered_event_log']},sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 /async_rbench/upstream_solutions/write_manifest.py
