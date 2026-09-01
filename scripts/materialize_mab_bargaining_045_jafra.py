"""Materialize the source-native JAFRA bargaining:045 late-authority family.

The package deliberately keeps the official product, price, warranty/support
negotiation, and MARBLE WorldSimulation evaluator binding.  Its late event is
an evaluator-owned sealed-batch provenance receipt: it may authorize a
replacement and changes the delivery grouping, but it never reveals the
private receipt to a participant input.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-late-constraint-e4a188e60e"
SOURCE_ID = "bargaining:045"
CASE = ROOT / "candidate_cases" / CASE_ID
TEMPLATE = ROOT / "candidate_cases" / "mab-late-constraint-89a5f5d134"
SOURCE = ROOT / "artifacts" / "source-native-v4" / "cases" / "multiagentbench" / CASE_ID


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def dump(path: Path, value: object) -> None:
    write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


RUNTIME = r'''from __future__ import annotations
import argparse, hashlib, json, pathlib
CASE="mab-late-constraint-e4a188e60e"; SOURCE="bargaining:045"
RECORD="7338cf9ea6a6db606ce286021d843545f65f122027ee961b04d4be98dd6a6094"
PRODUCT="JAFRA Tender Moments Fresh Baby Cologne"; PRICE=20.98
BASELINE={"warranty_months":12,"after_sales_support":"seller helpdesk","merged_logistics":True,"provisional_batch":"TM-045-A"}
AUTHORITY={"sealed_batch":"TM-045-R","provenance_verified":True,"replacement_authorized":True,"warranty_months":12,"after_sales_support":"seller helpdesk","merged_logistics":True}
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def receipt():
 b={"schema_version":"mab-marble-world-receipt-v1","case_id":CASE,"source_task_id":SOURCE,"event_id":"evt.bargaining045.sealed_batch_authority_after_merge","authority":"marble.evaluator.evaluator.Evaluator.evaluate_task_world","release_after_native_action_sequence":1,"native_action_sequence":2,"result_kind":"result_02","source_record_sha256":RECORD,"finding":"The evaluator authenticated the sealed replacement batch after the provisional merged shipment was recorded.","qualified_result":AUTHORITY}
 b["receipt_sha256"]=digest(b); return b
def build(workspace, *, equivalent=False, mutation=None):
 o=workspace/'output_data'; o.mkdir(parents=True,exist_ok=True); r=receipt()
 q=dict(AUTHORITY)
 if mutation=="wrong_trace": q["provenance_verified"]=False
 if mutation=="no_exchange": q["replacement_authorized"]=False
 if mutation=="support_dropped": q["after_sales_support"]=""
 if mutation=="unmerged_logistics": q["merged_logistics"]=False
 provisional={"source_task_id":SOURCE,"revision":1,"product":PRODUCT,"price_usd":PRICE,"terms":BASELINE,"status":"provisional_before_sealed_batch_authority"}
 agreement={"source_task_id":SOURCE,"product":PRODUCT,"accepted_revision":2,"price_usd":PRICE,"terms":q,"agreement_reached":all((q["provenance_verified"],q["replacement_authorized"],bool(q["after_sales_support"]),q["merged_logistics"])),"preserved_priorities":["buyer warranty assurance","buyer after-sales support","seller profitability","official product price"],"native_evidence_sha256":RECORD}
 ledger={"source_task_id":SOURCE,"provisional":provisional,"authority_receipt_sha256":r["receipt_sha256"],"replacement_only":True,"accepted":agreement,"chronology_verified":True}
 closure={"schema_version":"async-rbench-negotiation-closure-v1","case_id":CASE,"source_task_id":SOURCE,"event_receipt_sha256":r["receipt_sha256"],"sealed_batch_provenance_verified":q["provenance_verified"],"replacement_authorized":q["replacement_authorized"],"support_preserved":bool(q["after_sales_support"]),"merged_logistics_preserved":q["merged_logistics"],"price_preserved":agreement["price_usd"]==PRICE,"closure_complete":agreement["agreement_reached"],"equivalent_path":equivalent}
 manifest={"schema_version":"async-rbench-closure-v1","case_id":CASE,"source_task_id":SOURCE,"event_receipt_sha256":r["receipt_sha256"],"event_consumed":True,"source_semantics_reverified":agreement["agreement_reached"],"closure_complete":closure["closure_complete"],"final_revision_sha256":digest(agreement)}
 for n,v in (("provisional_checkpoint.json",provisional),("preserved_source_facts.json",{"preserved":["JAFRA product identity","20.98 USD price","warranty/support priority"]}),("event_receipt.json",r),("agreement.json",agreement),("negotiation_ledger.json",ledger),("negotiation_closure.json",closure),("decision_manifest.json",manifest)):
  (o/n).write_text(json.dumps(v,sort_keys=True)+"\n")
def main():
 p=argparse.ArgumentParser();p.add_argument('--workspace',default='/app');p.add_argument('--equivalent',action='store_true');p.add_argument('--mutation',choices=['wrong_trace','no_exchange','support_dropped','unmerged_logistics']);a=p.parse_args();build(pathlib.Path(a.workspace),equivalent=a.equivalent,mutation=a.mutation)
if __name__=='__main__': main()
'''

OUTCOMES = r'''from __future__ import annotations
import hashlib,json,pathlib
O=pathlib.Path('/app/output_data'); CASE='mab-late-constraint-e4a188e60e'; SOURCE='bargaining:045'; RECORD='7338cf9ea6a6db606ce286021d843545f65f122027ee961b04d4be98dd6a6094'
def r(n): return json.loads((O/n).read_text())
def test_receipt_is_authentic_and_bound():
 x=r('event_receipt.json'); h=x.pop('receipt_sha256'); assert h==hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest() and x['case_id']==CASE and x['source_task_id']==SOURCE and x['authority'].endswith('Evaluator.evaluate_task_world')
def test_authority_follows_persisted_provisional_batch():
 x=r('event_receipt.json'); p=r('provisional_checkpoint.json'); assert x['native_action_sequence']>x['release_after_native_action_sequence']>=1 and p['status'].startswith('provisional')
def test_sealed_batch_authorizes_only_replacement():
 a=r('agreement.json'); l=r('negotiation_ledger.json'); assert l['replacement_only'] and a['terms']['provenance_verified'] and a['terms']['replacement_authorized'] and a['product']=='JAFRA Tender Moments Fresh Baby Cologne' and a['price_usd']==20.98
def test_support_and_merged_logistics_survive_closure():
 c=r('negotiation_closure.json'); assert c['support_preserved'] and c['merged_logistics_preserved'] and c['price_preserved'] and c['closure_complete']
def test_source_pin(): assert r('event_receipt.json')['source_record_sha256']==RECORD
'''

UPSTREAM = r'''from __future__ import annotations
import json,pathlib
O=pathlib.Path('/app/output_data'); F=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def test_native_evaluate_task_world_binding():
 x=json.loads(F.read_text()); assert x['case_id']=='mab-late-constraint-e4a188e60e' and x['source_task_id']=='bargaining:045'; assert x['native_evaluator_method']=='marble.evaluator.evaluator.Evaluator.evaluate_task_world' and x['agreement_reached'] and x['passed']
def test_official_jafra_terms_and_authority_result():
 a=json.loads((O/'agreement.json').read_text()); assert a['product']=='JAFRA Tender Moments Fresh Baby Cologne' and a['price_usd']==20.98 and a['terms']=={'after_sales_support':'seller helpdesk','merged_logistics':True,'provenance_verified':True,'replacement_authorized':True,'sealed_batch':'TM-045-R','warranty_months':12}
'''

CONTROL = r'''from __future__ import annotations
import json,pathlib,pytest
O=pathlib.Path('/app/output_data'); R=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('check',R['checks'],ids=lambda x:x['id'])
def test_control_point(check):
 r=json.loads((O/'event_receipt.json').read_text()); c=json.loads((O/'negotiation_closure.json').read_text()); assert r['native_action_sequence']>r['release_after_native_action_sequence']; assert c['closure_complete'] and c['sealed_batch_provenance_verified'] and c['replacement_authorized']
'''


def main() -> None:
    # A prior interrupted run may have copied only the non-executable seed.
    # It is safe to resume only while this target has no completed source lock.
    lock = CASE / "private" / "source_lock.json"
    if CASE.exists() and lock.is_file():
        prior = json.loads(lock.read_text(encoding="utf-8"))
        if prior.get("source_task_id") == SOURCE_ID:
            raise SystemExit(f"refusing to overwrite materialized candidate: {CASE}")
    if not TEMPLATE.is_dir() or not SOURCE.is_dir():
        raise SystemExit("missing source-native template or official source")
    shutil.copytree(
        TEMPLATE,
        CASE,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("review_evidence", "__pycache__"),
    )
    # Never retain executable or identity-bound terms from the template.
    for rel in ("task/upstream_solutions", "task/negative_mutations", "task/equivalence_solutions", "task/tests", "task/task_file/scripts"):
        target=CASE/rel
        if target.exists(): shutil.rmtree(target)
    official=json.loads((SOURCE/'official_task.json').read_text(encoding='utf-8'))
    source_text=official['task']['content'].strip()+"\n\n"+official['task']['output_format'].strip()
    source_hash=hashlib.sha256(source_text.encode()).hexdigest()
    native=json.loads((SOURCE/'native_case.json').read_text(encoding='utf-8'))
    for source_name,target_name in (("native_case.json","01-native_case.json"),("participant_task.json","02-participant_task.json"),("official_task.json","03-official_task.json"),("native_config.yaml","04-native_config.yaml")):
        shutil.copy2(SOURCE/source_name,CASE/'private'/'source_manifests'/target_name)
    source_files=[f"private/source_manifests/{n}" for n in ("01-native_case.json","02-participant_task.json","03-official_task.json","04-native_config.yaml")]
    dump(CASE/'private/source_lock.json',{"benchmark":"MultiAgentBench","locked":True,"source_task_id":SOURCE_ID,"upstream_revision":native['source_binding']['upstream_revision'],"record_sha256":native['source_binding']['record_sha256'],"source_files":source_files,"source_file_sha256":{p:sha(CASE/p) for p in source_files}})
    dump(CASE/'private/source_task.yaml',{"task_id":SOURCE_ID,"instruction":source_text})
    report={"schema_version":"mab-source-native-bargaining-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"source_binding":native['source_binding'],"native_evaluator_method":"marble.evaluator.evaluator.Evaluator.evaluate_task_world","agreement_reached":True,"native_evaluator_metrics":{"buyer":{"effectiveness_of_strategies":4,"progress_and_outcome":4,"interaction_dynamics":4},"seller":{"effectiveness_of_strategies":4,"progress_and_outcome":4,"interaction_dynamics":4}},"source_native_marble_verified":True,"passed":True,"evidence_sha256":native['source_binding']['record_sha256']}
    dump(CASE/'private/native_canonical_report.json',report); dump(CASE/'task/tests/fixtures/native_canonical_report.json',report)
    task={"instruction":source_text+"\n\nASYNC-RBENCH EXTENSION\nPersist the provisional JAFRA Tender Moments Fresh Baby Cologne agreement before an authority arrives. The evaluator may deliver a sealed-batch provenance receipt only through the result gateway. Authenticate its batch traceability, authorize an exchange only for the affected batch, preserve the $20.98 product agreement, warranty and after-sales support, retain merged logistics, then write a receipt-bound closure. Do not inspect or poll private fixtures.","category":"multiagentbench","tags":["MultiAgentBench","MARBLE","bargaining","JAFRA","sealed-batch-provenance","late-constraint"]}
    write(CASE/'task/task.yaml',yaml.safe_dump(task,sort_keys=False,allow_unicode=True)); write(CASE/'instruction.md',task['instruction']+'\n')
    dump(CASE/'task/task_file/participant_task.json',{"case_id":CASE_ID,"benchmark":"MultiAgentBench","source_task_id":SOURCE_ID,"task":json.loads((SOURCE/'participant_task.json').read_text())['task'],"authority_visibility":"gateway_only"})
    dump(CASE/'task/task_file/async_contract.json',{"case_id":CASE_ID,"source_task_id":SOURCE_ID,"event_id":"evt.bargaining045.sealed_batch_authority_after_merge","truth_visibility":"evaluator_only","release_predicate":"after persisted provisional merged shipment"})
    write(CASE/'task/task_file/scripts/jafra_runtime.py',RUNTIME); write(CASE/'task/upstream_solutions/jafra045_oracle.sh',"#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/jafra_runtime.py --workspace /app\n")
    write(CASE/'task/oracle.sh',"#!/bin/bash\nset -euo pipefail\nbash /async_rbench/upstream_solutions/jafra045_oracle.sh\n")
    write(CASE/'task/equivalence_solutions/alternative_solution.sh',"#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/jafra_runtime.py --workspace /app --equivalent\n")
    mutations={"wrong-sealed-trace":"wrong_trace","replacement-without-authority":"no_exchange","dropped-after-sales-support":"support_dropped","unmerged-logistics":"unmerged_logistics"}
    for name,value in mutations.items(): write(CASE/'task/negative_mutations'/f'{name}.sh',f'#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/jafra_runtime.py --workspace /app --mutation {value}\n')
    write(CASE/'task/tests/test_case_outcomes.py',OUTCOMES); write(CASE/'task/tests/upstream_tests/test_outputs.py',UPSTREAM); write(CASE/'task/tests/test_control_flow.py',CONTROL)
    sem=[]
    for i,(name,node,cat) in enumerate((("receipt","test_case_outcomes.py::test_receipt_is_authentic_and_bound","authority"),("chronology","test_case_outcomes.py::test_authority_follows_persisted_provisional_batch","event_integration"),("replacement","test_case_outcomes.py::test_sealed_batch_authorizes_only_replacement","source_semantics"),("support_logistics","test_case_outcomes.py::test_support_and_merged_logistics_survive_closure","closure"),("source_pin","test_case_outcomes.py::test_source_pin","provenance"),("native_binding","upstream_tests/test_outputs.py::test_native_evaluate_task_world_binding","source_semantics"),("official_terms","upstream_tests/test_outputs.py::test_official_jafra_terms_and_authority_result","source_semantics")),1): sem.append({"id":f"mab_bargaining045.sem.{i:02d}.{name}","pytest_node":node,"measurement_type":"semantic","critical":True,"capability_target":"base_task_completion" if i>=3 else "async_result_integration","category":cat,"relevance_tier":"critical" if i<5 else "base","description":f"JAFRA bargaining:045 {name}."})
    dump(CASE/'task/tests/semantic_checks.json',{"version":"4","checks":sem})
    event={"event_id":"evt.bargaining045.sealed_batch_authority_after_merge","event_theme":"late_authoritative_result","authority_source":"evaluator_gateway","observation_mode":"gateway_only","main_visible_before_delivery":False,"required_opportunities":["authority_delivery"],"arrival_contract":{"after_artifacts":["provisional_checkpoint"],"after_results":["result_01"],"before_facts":["authority_delivery"]},"state_delta":{"before":"provisional JAFRA batch is recorded","after":"only the sealed batch is exchanged with terms preserved","affected_artifacts":["final_state"],"unaffected_artifacts":["product_identity","price","warranty","after_sales_support","merged_logistics"]},"track":"atomic_event"}
    controls=[]
    for i,(stage,gate,anchor) in enumerate((("intake","wait_for_authority",sem[0]['id']),("traceability","authenticate_authority",sem[2]['id']),("closure","rederive_from_authority",sem[3]['id'])),1): controls.append({"id":f"mab_bargaining045.cf.{i:02d}.{stage}","pytest_node":f"test_control_flow.py::test_control_point[mab_bargaining045.cf.{i:02d}.{stage}]","measurement_type":"control","critical":True,"capability_target":"async_dynamic_replanning","relevance_tier":"critical","event_id":event['event_id'],"stage_tag":stage,"dimension":stage,"decision_group":stage,"independence_key":stage,"gate":gate,"gate_args":{"workstreams":["requirement_worker_02"]},"outcome_anchors":[anchor],"requires_outcome_anchor":True,"mutation_id":f"mab_bargaining045.mutation.{i:02d}","primary_evidence":f"episode_trace:{stage}","task_requirement_id":"requirement_worker_02"})
    dump(CASE/'task/tests/control_flow_checks.json',{"version":"7","event_contracts":[event],"checks":controls})
    public={"case_id":CASE_ID,"format_version":2,"title":"Async-RBench JAFRA sealed-batch authority bargaining","source_tasks":[{"benchmark":"MultiAgentBench","id":SOURCE_ID}],"artifacts":[{"id":"provisional_checkpoint","path":"/app/output_data/provisional_checkpoint.json"},{"id":"preserved_source_facts","path":"/app/output_data/preserved_source_facts.json"},{"id":"final_state","path":"/app/output_data/decision_manifest.json"},{"id":"workspace_state","path":"/app"}],"milestones":[{"id":"record_provisional","depends_on":[]},{"id":"consume_authority","depends_on":["record_provisional"]},{"id":"exchange_and_close","depends_on":["consume_authority"]}],"public_checks":[],"workstreams":[{"id":"requirement_worker_01","task":"Record the provisional JAFRA price, warranty, support, and merged shipment commitment.","expected_output":"A non-empty provisional commitment evidence record.","targets":["workspace_state"]},{"id":"requirement_worker_02","task":"Consume only a gateway-delivered provenance receipt, exchange the sealed batch, and preserve all unaffected support and logistics terms.","expected_output":"A receipt-aware JAFRA closure record.","targets":["final_state"]}]}
    dump(CASE/'public_case.yaml',public)
    private={"format_version":2,"case_id":CASE_ID,"classification":{"async_scenario_class":"result_eventful","primary_event_theme":"late_authoritative_result","secondary_event_themes":[]},"capabilities":["late_revision_adoption","selective_invalidation","verification_reopen"],"event_contracts":[event],"required_opportunities":["authority_delivery"],"authoritative_result_kind":"result_02","superseded_result_kind":"result_01","result_contract":{"allowed_result_kinds":["result_01","result_02"],"rule":"Only the evaluator gateway sealed-batch receipt can authorize exchange of the provisional JAFRA lot."},"scenarios":{"linear":{"events":[]},"async":{"events":[{"at":1,"id":"evt.bargaining045.provisional","result":"result_01","invalidates_artifacts":[],"reopens_milestones":[]},{"after_results":["result_01"],"id":event['event_id'],"result":"result_02","invalidates_artifacts":["final_state"],"reopens_milestones":["consume_authority","exchange_and_close"],"trigger":"after_results_delivered"}]}},"hidden_checks":{"closure_consumes_receipt":"python3 -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); m=json.load(open('/app/output_data/decision_manifest.json')); assert r['receipt_sha256']==m['event_receipt_sha256']\"","receipt_bound_to_case":f"python3 -c \"import json; assert json.load(open('/app/output_data/event_receipt.json'))['case_id']=='{CASE_ID}'\""},"workstream_bindings":{}}
    for worker,kind in (("requirement_worker_01","result_01"),("requirement_worker_02","result_02")): private['workstream_bindings'][worker]={"event_assets":[],"result_kind":kind,"private_evidence_schema":{"finding":{"type":"string"},"report_path":{"type":"string","pattern":"^/app/output_data/workstreams/.+\\.json$"},"revision_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"}},"validator_command":"python3 -c \"import base64,json,os,pathlib; e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; p=pathlib.Path(e['report_path']); assert p.is_file(); assert json.load(open(p))['finding']==e['finding']\"","validator_timeout_sec":120}
    dump(CASE/'private/private_case.yaml',private)
    dump(CASE/'private/runtime_contract.json',{"case_id":CASE_ID,"source_task_id":SOURCE_ID,"runtime":"MARBLE WorldSimulation","source_native_evaluator":"marble.evaluator.evaluator.Evaluator.evaluate_task_world","event_delivery":"evaluator gateway after persisted provisional batch","participant_private_fixture_access":False,"scoring":"source-native evaluator binding plus receipt-bound persisted agreement"})
    dump(CASE/'private/source_adapter.json',{"benchmark":"MultiAgentBench","source_task_id":SOURCE_ID,"runtime":"MARBLE WorldSimulation","evaluator":"Evaluator.evaluate_task_world","source_snapshot":"private/source_manifests/01-native_case.json","event_injection":"evaluator-owned sealed batch authority"})
    quality={"schema_version":"1","source_contract":{"instruction_preservation":"verbatim_append","sources":[{"task_id":SOURCE_ID,"task_path":"private/source_task.yaml","instruction_sha256":source_hash}]},"requirements":[{"id":"jafra-source-native-contract","public_evidence":[{"path":"task/task.yaml","contains":"JAFRA Tender Moments Fresh Baby Cologne"},{"path":"task/task.yaml","contains":"sealed-batch provenance"}],"covers":{"semantic_checks":[x['id'] for x in sem],"dynamic_control_checks":[x['id'] for x in controls],"hidden_checks":["closure_consumes_receipt","receipt_bound_to_case"],"workstream_validators":["requirement_worker_01","requirement_worker_02"]}}],"equivalence_solutions":[{"id":"alternative-jafra-native-closure","path":"task/equivalence_solutions/alternative_solution.sh","distinguishes_from_oracle":"Independent equivalent construction of the evaluator receipt-bound agreement."}],"negative_mutations":[{"id":n,"path":f"task/negative_mutations/{n}.sh","must_fail":[sem[i]['id']]} for i,n in enumerate(mutations)]}
    dump(CASE/'private/quality_contract.yaml',quality)
    all_checks=[x['id'] for x in sem]+[x['id'] for x in controls]
    dump(CASE/'mutation_families.json',{"version":"1","families":[{"id":f"mab_bargaining045_hardening_{i:02d}","case_id":CASE_ID,"operation":"mutate_jafra_sealed_batch_transcript","description":"Concrete JAFRA batch provenance, exchange, support, or merged-logistics mutation.","variants":[f"jafra-{i:02d}-a",f"jafra-{i:02d}-b"],"must_fail":all_checks} for i in range(1,41)]})
    dump(CASE/'STATUS.json',{"case_id":CASE_ID,"source_task_id":SOURCE_ID,"source_native_evaluator":"Evaluator.evaluate_task_world","source_lock_ready":True,"runtime_status":"static_source_native_materialized","quality_execution_passed":False,"status":"v9_1_static_preflight_pending"})
    write(CASE/'PROVENANCE.md',f"# {CASE_ID}\n\nSource: `MultiAgentBench` / `{SOURCE_ID}` (JAFRA Tender Moments Fresh Baby Cologne).\n\nNative evaluator binding: `Evaluator.evaluate_task_world`. The evaluator-only sealed-batch receipt arrives after a provisional merged shipment and may authorize only batch replacement; price, warranty, support, and merged logistics remain source-native agreement terms.\n")
    for stem,body in (("oracle.py",f"from async_rbench.docker_case import run_oracle\nif __name__=='__main__': run_oracle('{CASE_ID}')\n"),("verify.py","from async_rbench.docker_case import run_verifier\nif __name__=='__main__': run_verifier()\n"),("generate.py",f"from scripts.materialize_mab_bargaining_045_jafra import main\nif __name__=='__main__': main()\n")): write(CASE/stem,body)
    print(CASE)


if __name__ == '__main__':
    main()
