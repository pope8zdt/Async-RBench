"""Restore the frozen V9.1 schema for the JAFRA bargaining:045 candidate."""
from __future__ import annotations
import hashlib, json, shutil
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from async_rbench.case_quality import instruction_sha256

C=ROOT/'candidate_cases/mab-late-constraint-e4a188e60e'
B=ROOT/'candidate_cases/rebuild-to-200/blueprints/mab-late-constraint-e4a188e60e'
S=ROOT/'artifacts/source-native-v4/cases/multiagentbench/mab-late-constraint-e4a188e60e'

def main():
    # These are the frozen producer-facing V7/V9.1 ledgers.  The JAFRA source
    # identifiers already match, so copying cannot import another case's terms.
    for rel in ('public_case.yaml','mutation_families.json','private/private_case.yaml',
                'private/dynamic_point_plan.json','private/quality_contract.yaml',
                'private/score_plan.json','private/case_ir.json','private/event_policy.json'):
        shutil.copy2(B/rel,C/rel)
    # The quality contract hashes official task *content* through the canonical
    # instruction normalizer; preserve the frozen V9.1 ledger around that value.
    q=json.loads((C/'private/quality_contract.yaml').read_text(encoding='utf-8'))
    content=json.loads((S/'official_task.json').read_text(encoding='utf-8'))['task']['content']
    q['source_contract']['sources'][0]['instruction_sha256']=instruction_sha256(content)
    (C/'private/quality_contract.yaml').write_text(json.dumps(q,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    # Runtime metadata is case-local and must advertise the actual bargaining evaluator.
    lock=json.loads((C/'private/source_lock.json').read_text(encoding='utf-8'));lock['production_case_path']='.'
    (C/'private/source_lock.json').write_text(json.dumps(lock,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    public=json.loads((C/'public_case.yaml').read_text(encoding='utf-8'));public['implementation']='real-instance-derived';public['task_instruction_path']='task/task.yaml'
    (C/'public_case.yaml').write_text(json.dumps(public,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    status=json.loads((C/'STATUS.json').read_text(encoding='utf-8'));status['status']='v9_1_schema_rebound_pending_quality';status['quality_execution_passed']=False
    (C/'STATUS.json').write_text(json.dumps(status,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    # The runtime stays JAFRA-specific; these are merely the blueprint's frozen
    # executable registry IDs, each tied to a concrete local assertion.
    checks=[]
    nodes=[
      ('event.receipt','test_case_outcomes.py::test_receipt_is_authentic_and_bound','async_result_integration','event_integration','critical'),
      ('event.probes','test_case_outcomes.py::test_authority_follows_persisted_provisional_batch','async_result_integration','event_integration','critical'),
      ('closure','test_case_outcomes.py::test_support_and_merged_logistics_survive_closure','async_consistency_closure','closure','critical'),
      ('source.pin','test_case_outcomes.py::test_source_pin','base_task_completion','provenance','base'),
      ('source.native_binding','upstream_tests/test_outputs.py::test_native_evaluate_task_world_binding','base_task_completion','source_semantics','base'),
      ('source.core_behavior','test_case_outcomes.py::test_sealed_batch_authorizes_only_replacement','base_task_completion','source_semantics','base'),
      ('source.event_behavior','upstream_tests/test_outputs.py::test_final_jafra_terms_follow_authority','base_task_completion','source_semantics','base'),
      ('source.edge_behavior','test_case_outcomes.py::test_untrusted_batch_is_not_authoritative','base_task_completion','source_semantics','base'),
      ('source.preservation','test_case_outcomes.py::test_preserved_source_priorities_are_exact','base_task_completion','source_semantics','base'),
      ('source.final_terms','upstream_tests/test_outputs.py::test_official_jafra_terms_and_authority_result','base_task_completion','source_semantics','base'),]
    for suffix,node,target,category,tier in nodes:
        checks.append({'id':f'mab_late_constraint_e4a188e60e.{suffix}','pytest_node':node,'measurement_type':'semantic','critical':True,'capability_target':target,'category':category,'relevance_tier':tier,'description':f'JAFRA bargaining:045 {suffix}.'})
    (C/'task/tests/semantic_checks.json').write_text(json.dumps({'version':'4','checks':checks},indent=2,sort_keys=True)+'\n',encoding='utf-8')
    task=json.loads((B/'task/task.yaml').read_text(encoding='utf-8'))
    (C/'task/task.yaml').write_text(json.dumps(task,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    source=json.loads((S/'official_task.json').read_text(encoding='utf-8'))['task']['content']
    (C/'private/source_task.yaml').write_text(json.dumps({'task_id':'bargaining:045','instruction':source},indent=2,sort_keys=True)+'\n',encoding='utf-8')
    q=json.loads((C/'private/quality_contract.yaml').read_text(encoding='utf-8'))
    paths=['wrong-sealed-trace.sh','replacement-without-authority.sh','dropped-after-sales-support.sh','unmerged-logistics.sh']
    for item,path in zip(q['negative_mutations'],paths): item['path']='task/negative_mutations/'+path
    (C/'private/quality_contract.yaml').write_text(json.dumps(q,indent=2,sort_keys=True)+'\n',encoding='utf-8')
if __name__=='__main__': main()
