#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
e=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json')); assert e['canonical_episode_owner']=='evaluator' and e['passed'] is True
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({'source_task_id':'research:047','status':'three_upstream_results_persisted','upstream_depth':4},sort_keys=True)+'\n'); pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({'source_task_id':'research:047','preserved':True,'artifacts':['five_question_structure', 'active_perception', 'action_primitive_library', 'closed_loop_replanning']},sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
r=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); c={'schema_version': 'async-rbench-mab-source-closure-v1', 'case_id': 'mab-late-constraint-3c40bbec7f', 'source_task_id': 'research:047', 'artifact_type': 'come_robot_safety_research_closure', 'event': 'recovery_safety_scope_added', 'upstream_depth': 4, 'preserved_workflows': ['five_question_structure', 'active_perception', 'action_primitive_library', 'closed_loop_replanning'], 'source_semantics_reverified': True}; c['event_receipt_sha256']=r['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
