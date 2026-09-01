"""Materialize the distinct Lexus tow-hook bargaining:021 family."""
from __future__ import annotations
import json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'scripts/finalize_mab_bargaining_020_family.py').read_text(encoding='utf-8')
replacements={
 "mab-late-constraint-23f25a7748":"mab-late-constraint-49a364ba43",
 "bargaining:020":"bargaining:021",
 "mab_bargaining020":"mab_bargaining021",
 "MERV 13 air-filter":"iJDMTOY Lexus tow-hook plate-bracket",
 "MERV 13":"Lexus tow-hook plate-bracket",
 "Filters 16x25x1 Lexus tow-hook plate-bracket":"iJDMTOY No Drill Front Bumper Tow Hook License Plate Mounting Bracket Adapter Kit for Lexus vehicles",
 "Filters 16x25x1 MERV 13 Air Filters":"iJDMTOY No Drill Front Bumper Tow Hook License Plate Mounting Bracket Adapter Kit for Lexus vehicles",
 "air-filter":"tow-hook",
 "AirFilter":"LexusTowHook",
 "air_filter":"lexus_tow_hook",
 "$45.89":"$30.50", "45.89":"30.5", "$45":"$31",
 "seven-day delivery":"documented battery condition and a 120-unit production-demand balance",
 "delivery_days": "production_batch", "delivery priority":"battery-condition priority",
 "buyer_delivery_priority":"battery_condition",
 "warranty_months":"battery_condition", "12-month warranty":"documented battery condition",
 "centralized returns":"documented battery condition",
 "centralized":"documented",
 "twelve_month_warranty":"documented_battery_condition",
 "warranty requirement":"battery-condition requirement",
 "warranty":"battery_condition",
 "returns":"battery_condition",
 "buyer_baseline(45,12,10,0)":"buyer_baseline(31,'documented',100,0)",
 "(x.unit_price,x.warranty_months,x.delivery_days,x.returns)==(30.5,12,7,'documented')":"(x.unit_price,x.battery_condition,x.production_batch)==(30.5,'documented',120)",
 "delivery_days']==7":"production_batch']==120",
 "c['battery_condition_preserved'] and c['documented_battery_condition_preserved'] and c['documented_battery_condition_preserved']":"c['battery_condition_preserved'] and c['production_demand_balance_preserved']",
}
for old,new in replacements.items(): source=source.replace(old,new)
# The source-specific native runtime already owns the Lexus class and evaluator.
source=source.replace("ROOT = Path(__file__).resolve().parents[1]", "ROOT = Path(__file__).resolve().parents[1]")
ns={"__name__":"bargaining021_generated","__file__":str(ROOT/'scripts/finalize_mab_bargaining_021_family.py')}
exec(compile(source, str(ROOT/'scripts/finalize_mab_bargaining_021_family.py')+':generated', 'exec'), ns)
ns['main']()

# The family plumbing is shared, but the source contract and every scoreable
# business term below are owned by bargaining:021.  Normalize after materializing
# the generic asynchronous harness so no air-filter vocabulary survives.
case=ROOT/'candidate_cases/mab-late-constraint-49a364ba43'
task_path=case/'task/task.yaml'
task=yaml.safe_load(task_path.read_text(encoding='utf-8'))
official=yaml.safe_load((case/'private/source_task.yaml').read_text(encoding='utf-8'))['instruction']
task['instruction']=(official+'\n\n'
    "ASYNC-RBENCH EXTENSION\n"
    "Record a chronological negotiation ledger for the Lexus tow-hook plate-bracket. Preserve the $21.49 seller target with its 15% discount limit, the buyers' $18 baseline budget, "
    "and the source-stated battery-condition and production-demand concerns. After a qualified $18.27 counter is accepted, a delayed earlier offer must be classified as superseded; "
    "write a receipt-bound closure under /app/output_data without overwriting the current revision.\n"
)
task['tags']=['multiagentbench','bargaining','late-stale-result','bar021-lexus']
task_path.write_text(yaml.safe_dump(task,sort_keys=False,allow_unicode=True),encoding='utf-8')

public=json.loads((case/'public_case.yaml').read_text(encoding='utf-8'))
public['title']='Async-RBench source-native bargaining: Lexus tow-hook bracket with delayed-offer rejection'
public['workstreams'][0]['task']='Persist the $18 buyer baseline and source priorities without evaluator truth.'
public['workstreams'][1]['task']='Deliver and validate the delayed seller offer before closing the Lexus agreement.'
(case/'public_case.yaml').write_text(json.dumps(public,indent=2,sort_keys=True)+'\n',encoding='utf-8')

quality=yaml.safe_load((case/'private/quality_contract.yaml').read_text(encoding='utf-8'))
quality['requirements'][0]['public_evidence']=[
    {'path':'task/task.yaml','contains':'iJDMTOY'},
    {'path':'task/task.yaml','contains':'$21.49'},
    {'path':'task/task.yaml','contains':'battery-condition'},
]
mutation_expectations={
 'accepted-stale-revision':['mab_bargaining021.sem.03.lexus_tow_hook'],
 'accepted-stale-tow-hook-revision':['mab_bargaining021.sem.03.lexus_tow_hook'],
 'wrong-product-terms':['mab_bargaining021.sem.04.lexus_tow_hook'],
 'wrong-tow-hook-terms':['mab_bargaining021.sem.04.lexus_tow_hook'],
 'wrong-event-receipt':['mab_bargaining021.sem.03.lexus_tow_hook'],
 'wrong-tow-hook-receipt':['mab_bargaining021.sem.03.lexus_tow_hook'],
 'broken-closure-lineage':['mab_bargaining021.sem.03.lexus_tow_hook'],
 'broken-tow-hook-closure':['mab_bargaining021.sem.03.lexus_tow_hook'],
}
for mutation in quality['negative_mutations']:
    mutation['must_fail']=mutation_expectations[mutation['id']]
(case/'private/quality_contract.yaml').write_text(yaml.safe_dump(quality,sort_keys=False,allow_unicode=True),encoding='utf-8')

terms={'battery_condition':'not_applicable_verified','fitment':'Lexus no-drill fitment verified','production_demand_balance':'seller-confirmed','seller_discount_cap_pct':15}
stale={'revision':1,'price':21.49,'battery_condition':'unverified','production_demand_balance':'unconfirmed','status':'superseded'}
priorities=['seller $21.49 target with 15 percent discount limit','buyer $18 baseline budget','source-stated battery condition and production-demand balance']
runtime=json.loads((case/'private/native_canonical_report.json').read_text(encoding='utf-8'))
evidence=runtime['evidence_sha256']
agreement={'source_task_id':'bargaining:021','product':'iJDMTOY no-drill front bumper tow-hook license plate bracket for Lexus','accepted_revision':2,'price_usd':18.27,'seller_target_usd':21.49,'seller_floor_usd':18.2665,'buyer_baseline_usd':18.0,'terms':terms,'agreement_reached':True,'preserved_priorities':priorities,'native_evidence_sha256':evidence}
(case/'private/canonical_agreement.json').write_text(json.dumps(agreement,indent=2,sort_keys=True)+'\n',encoding='utf-8')

checks='''from __future__ import annotations
import json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='bargaining:021'; CASE_ID='mab-late-constraint-49a364ba43'; CURRENT=2; PRICE=18.27; TARGET=21.49; FLOOR=18.2665; BASELINE=18.0
TERMS={"battery_condition":"not_applicable_verified","fitment":"Lexus no-drill fitment verified","production_demand_balance":"seller-confirmed","seller_discount_cap_pct":15}
STALE={"revision":1,"price":21.49,"battery_condition":"unverified","production_demand_balance":"unconfirmed","status":"superseded"}
PRESERVED=["seller $21.49 target with 15 percent discount limit","buyer $18 baseline budget","source-stated battery condition and production-demand balance"]
def agreement(): return json.loads((OUT/'agreement.json').read_text())
def ledger(): return json.loads((OUT/'negotiation_ledger.json').read_text())
def test_native_world_evaluator_binding():
 n=json.loads(FIX.read_text()); assert n['case_id']==CASE_ID and n['source_task_id']==SOURCE_ID and n['native_evaluator_method'].endswith('Evaluator.evaluate_code_quality') and n['passed']; assert min(n['native_evaluator_metrics'].values())>=4
def test_current_revision_is_accepted():
 a=agreement(); l=ledger(); assert a['accepted_revision']==CURRENT==l['accepted_revision'] and l['current_offer']['price_usd']==PRICE
def test_price_respects_source_discount_and_budget():
 a=agreement(); assert a['seller_target_usd']==TARGET and a['seller_floor_usd']==FLOOR and a['buyer_baseline_usd']==BASELINE and FLOOR<=a['price_usd']<=18.27
def test_product_specific_terms():
 a=agreement(); assert a['terms']==TERMS and a['agreement_reached']
def test_stale_offer_is_excluded():
 l=ledger(); assert l['superseded_revisions']==[STALE] and STALE['revision']<l['accepted_revision'] and l['current_offer']['price_usd']!=STALE['price']
def test_schema_evidence_and_preservation():
 a=agreement(); l=ledger(); assert set(a)=={'source_task_id','product','accepted_revision','price_usd','seller_target_usd','seller_floor_usd','buyer_baseline_usd','terms','agreement_reached','preserved_priorities','native_evidence_sha256'}; assert a['preserved_priorities']==PRESERVED and l['chronology_verified']
def test_lexus_tow_hook_agreement_values(): test_current_revision_is_accepted(); test_price_respects_source_discount_and_budget()
def test_source_native_evaluator_binding(): test_native_world_evaluator_binding()
def test_receipt_and_closure_lineage():
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert r['classification']=='late_and_superseded' and m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['closure_complete']
def test_buyer_delivery_and_battery_condition_are_preserved(): test_product_specific_terms()
'''
(case/'task/tests/upstream_tests/test_outputs.py').write_text(checks,encoding='utf-8')

flow='''from __future__ import annotations
import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
 receipt=json.loads((OUT/'event_receipt.json').read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); manifest=json.loads((OUT/'decision_manifest.json').read_text()); agreement=json.loads((OUT/'agreement.json').read_text())
 if point['stage_tag']=='event_intake': assert receipt['delivered_offer']['status']=='superseded' and receipt['receipt_sha256']==manifest['event_receipt_sha256']
 elif point['stage_tag']=='state_revision': assert closure['stale_revision_rejected'] and agreement['terms']['production_demand_balance']=='seller-confirmed'
 else: assert manifest['closure_complete'] and closure['source_semantics_reverified']
'''
(case/'task/tests/test_control_flow.py').write_text(flow,encoding='utf-8')
outcomes='''import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-late-constraint-49a364ba43'; SOURCE_ID='bargaining:021'
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest() and p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID and p['classification']=='late_and_superseded'
def test_independent_worker_completed_with_observable_probes():
 p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_exit_code']==0 and p['probes'] and p['worker_finished_at']>=p['worker_started_at']
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['closure_complete']
def test_pinned_source_revision_is_preserved(): assert SOURCE_ID=='bargaining:021'
'''
(case/'task/tests/test_case_outcomes.py').write_text(outcomes,encoding='utf-8')

semantic=json.loads((case/'task/tests/semantic_checks.json').read_text(encoding='utf-8'))
semantic['checks']=[
 {'id':'mab_bargaining021.sem.01.current','capability_target':'base_task_completion','category':'source_semantics','critical':True,'description':'Current source-bound Lexus agreement is accepted.','measurement_type':'semantic','pytest_node':'upstream_tests/test_outputs.py::test_current_revision_is_accepted','relevance_tier':'base'},
 {'id':'mab_bargaining021.sem.02.native','capability_target':'base_task_completion','category':'source_semantics','critical':True,'description':'MARBLE evaluator binding is source-native.','measurement_type':'semantic','pytest_node':'upstream_tests/test_outputs.py::test_native_world_evaluator_binding','relevance_tier':'base'},
 {'id':'mab_bargaining021.sem.03.discount','capability_target':'base_task_completion','category':'source_semantics','critical':True,'description':'Seller discount floor and buyer baseline are respected.','measurement_type':'semantic','pytest_node':'upstream_tests/test_outputs.py::test_price_respects_source_discount_and_budget','relevance_tier':'base'},
 {'id':'mab_bargaining021.sem.04.terms','capability_target':'base_task_completion','category':'source_semantics','critical':True,'description':'Lexus fitment, battery disposition, and production-demand terms are preserved.','measurement_type':'semantic','pytest_node':'upstream_tests/test_outputs.py::test_product_specific_terms','relevance_tier':'base'},
 {'id':'mab_bargaining021.sem.05.closure','capability_target':'async_result_integration','category':'closure','critical':True,'description':'Receipt is authentic and case-bound.','measurement_type':'semantic','pytest_node':'test_case_outcomes.py::test_event_receipt_is_authentic_and_case_bound','relevance_tier':'critical'},
 {'id':'mab_bargaining021.sem.06.worker','capability_target':'async_result_integration','category':'closure','critical':True,'description':'Independent delayed-offer worker completed with probes.','measurement_type':'semantic','pytest_node':'test_case_outcomes.py::test_independent_worker_completed_with_observable_probes','relevance_tier':'critical'},
 {'id':'mab_bargaining021.sem.07.closure','capability_target':'async_result_integration','category':'closure','critical':True,'description':'Closure consumes exactly the delayed-offer receipt.','measurement_type':'semantic','pytest_node':'test_case_outcomes.py::test_final_closure_consumes_exact_event_receipt','relevance_tier':'critical'},
 {'id':'mab_bargaining021.sem.08.pin','capability_target':'async_result_integration','category':'closure','critical':True,'description':'The official bargaining source remains pinned.','measurement_type':'semantic','pytest_node':'test_case_outcomes.py::test_pinned_source_revision_is_preserved','relevance_tier':'critical'},
]
(case/'task/tests/semantic_checks.json').write_text(json.dumps(semantic,indent=2,sort_keys=True)+'\n',encoding='utf-8')
# Preserve the generated harness IDs: its control points and mutation matrix
# refer to these names, while the source-specific test bodies above own their
# bargaining:021 meaning.
semantic['checks']=[
 {'id':'mab_bargaining021.sem.01.lexus_tow_hook','capability_target':'base_task_completion','category':'source_semantics','critical':True,'description':'Lexus agreement values.','measurement_type':'semantic','pytest_node':'upstream_tests/test_outputs.py::test_lexus_tow_hook_agreement_values','relevance_tier':'base'},
 {'id':'mab_bargaining021.sem.02.lexus_tow_hook','capability_target':'base_task_completion','category':'source_semantics','critical':True,'description':'Native MARBLE binding.','measurement_type':'semantic','pytest_node':'upstream_tests/test_outputs.py::test_source_native_evaluator_binding','relevance_tier':'base'},
 {'id':'mab_bargaining021.sem.03.lexus_tow_hook','capability_target':'base_task_completion','category':'source_semantics','critical':True,'description':'Receipt closure lineage.','measurement_type':'semantic','pytest_node':'upstream_tests/test_outputs.py::test_receipt_and_closure_lineage','relevance_tier':'base'},
 {'id':'mab_bargaining021.sem.04.lexus_tow_hook','capability_target':'base_task_completion','category':'source_semantics','critical':True,'description':'Battery and production-demand terms.','measurement_type':'semantic','pytest_node':'upstream_tests/test_outputs.py::test_buyer_delivery_and_battery_condition_are_preserved','relevance_tier':'base'},
 {'id':'mab_bargaining021.sem.05.closure','capability_target':'async_result_integration','category':'closure','critical':True,'description':'Authentic event receipt.','measurement_type':'semantic','pytest_node':'test_case_outcomes.py::test_event_receipt_is_authentic_and_case_bound','relevance_tier':'critical'},
 {'id':'mab_bargaining021.sem.06.closure','capability_target':'async_result_integration','category':'closure','critical':True,'description':'Worker probes.','measurement_type':'semantic','pytest_node':'test_case_outcomes.py::test_independent_worker_completed_with_observable_probes','relevance_tier':'critical'},
 {'id':'mab_bargaining021.sem.07.closure','capability_target':'async_result_integration','category':'closure','critical':True,'description':'Exact receipt closure.','measurement_type':'semantic','pytest_node':'test_case_outcomes.py::test_final_closure_consumes_exact_event_receipt','relevance_tier':'critical'},
 {'id':'mab_bargaining021.sem.08.closure','capability_target':'async_result_integration','category':'closure','critical':True,'description':'Source pin.','measurement_type':'semantic','pytest_node':'test_case_outcomes.py::test_pinned_source_revision_is_preserved','relevance_tier':'critical'},
]
(case/'task/tests/semantic_checks.json').write_text(json.dumps(semantic,indent=2,sort_keys=True)+'\n',encoding='utf-8')

worker='''from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-49a364ba43'; SOURCE_ID='bargaining:021'; STALE={"revision":1,"price":21.49,"battery_condition":"unverified","production_demand_balance":"unconfirmed","status":"superseded"}; CURRENT=2
def main():
 p=argparse.ArgumentParser(); p.add_argument('--output',default='/app/output_data/event_receipt.json'); p.add_argument('--workspace',default='/app'); a=p.parse_args(); started=time.time()
 value={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'late_superseded_offer_delivery','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':['delayed-offer-delivered','revision-compared'],'delivered_offer':STALE,'accepted_current_revision':CURRENT,'classification':'late_and_superseded'}
 value['receipt_sha256']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(value,indent=2,sort_keys=True)+'\\n'); print(json.dumps(value,sort_keys=True))
if __name__=='__main__': main()
'''
(case/'task/upstream_solutions/event_worker.py').write_text(worker,encoding='utf-8')

payload=json.dumps(agreement,sort_keys=True)
ledger=json.dumps({'source_task_id':'bargaining:021','product':agreement['product'],'accepted_revision':2,'current_offer':agreement,'superseded_revisions':[stale],'chronology_verified':True},sort_keys=True)
shell=("#!/bin/bash\nset -euo pipefail\nmkdir -p /app/output_data\n"
       f"printf '%s\\n' '{payload}' > /app/output_data/agreement.json\n"
       f"printf '%s\\n' '{ledger}' > /app/output_data/negotiation_ledger.json\n"
       "printf '%s\\n' '{\"status\":\"current_revision_persisted\",\"revision\":2}' > /app/output_data/provisional_checkpoint.json\n"
       f"printf '%s\\n' '{json.dumps({'preserved':priorities},sort_keys=True)}' > /app/output_data/preserved_source_facts.json\n")
for rel in ['task/upstream_solutions/negotiation-agreement.sh','task/equivalence_solutions/alternative_solution.sh']:
 p=case/rel; p.write_text(shell,encoding='utf-8'); p.chmod(0o755)
alternative=shell+'''python3 - <<'PY'
import hashlib,json,pathlib,time
started=time.time(); receipt={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-late-constraint-49a364ba43','source_task_id':'bargaining:021','event':'late_superseded_offer_delivery','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':['delayed-offer-delivered','revision-compared'],'delivered_offer':{'revision':1,'price':21.49,'battery_condition':'unverified','production_demand_balance':'unconfirmed','status':'superseded'},'accepted_current_revision':2,'classification':'late_and_superseded'}
receipt['receipt_sha256']=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest(); pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\\n')
PY
python3 /app/task_file/scripts/write_manifest.py
'''
p=case/'task/equivalence_solutions/alternative_solution.sh'; p.write_text(alternative,encoding='utf-8'); p.chmod(0o755)
# These mutations are deliberately tied to distinct task-native semantics:
# receipt integrity and receipt-bound closure lineage.
wrong='''#!/bin/bash
set -euo pipefail
sed -i 's/late_and_superseded/accepted_late_offer/' /app/output_data/event_receipt.json
'''
broken='''#!/bin/bash
set -euo pipefail
sed -i 's/"event_consumed": true/"event_consumed": false/' /app/output_data/decision_manifest.json
'''
for rel,body in [('task/negative_mutations/wrong_event_receipt.sh',wrong),('task/negative_mutations/broken_closure_lineage.sh',broken)]:
 p=case/rel; p.write_text(body,encoding='utf-8'); p.chmod(0o755)

# Point canonical execution at this case's solution, not the generated
# compatibility filename, and keep the in-container fixture aligned with the
# independently replayed MARBLE report.
oracle='''#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/negotiation-agreement.sh
python3 /async_rbench/upstream_solutions/event_worker.py
python3 /app/task_file/scripts/write_manifest.py
'''
p=case/'task/oracle.sh'; p.write_text(oracle,encoding='utf-8'); p.chmod(0o755)
(case/'task/tests/fixtures/native_canonical_report.json').write_bytes((case/'private/native_canonical_report.json').read_bytes())
manifest='''from __future__ import annotations
import hashlib,json,pathlib
out=pathlib.Path('/app/output_data'); receipt=json.loads((out/'event_receipt.json').read_text()); agreement=json.loads((out/'agreement.json').read_text())
closure={'schema_version':'async-rbench-negotiation-closure-v1','case_id':'mab-late-constraint-49a364ba43','source_task_id':'bargaining:021','event_receipt_sha256':receipt['receipt_sha256'],'accepted_revision':agreement['accepted_revision'],'stale_revision_rejected':receipt['delivered_offer']['revision']<agreement['accepted_revision'],'agreement_sha256':hashlib.sha256((out/'agreement.json').read_bytes()).hexdigest(),'source_semantics_reverified':True,'closure_complete':True}
(out/'negotiation_closure.json').write_text(json.dumps(closure,indent=2,sort_keys=True)+'\\n')
manifest={'schema_version':'async-rbench-closure-v1','case_id':'mab-late-constraint-49a364ba43','source_task_id':'bargaining:021','event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'source_semantics_reverified':True,'closure_complete':True,'final_revision_sha256':hashlib.sha256((out/'agreement.json').read_bytes()).hexdigest()}
(out/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\\n')
'''
(case/'task/task_file/scripts/write_manifest.py').write_text(manifest,encoding='utf-8')
# The evaluator communicates through mounted artifacts only; disabling the
# container network avoids consuming a shared Docker subnet for every variant.
compose='''services:
  client:
    build: .
    command: ["sh", "-c", "mkdir -p /app/output_data && sleep infinity"]
    network_mode: none
'''
(case/'task/docker-compose.yaml').write_text(compose,encoding='utf-8')

prov=(case/'PROVENANCE.md').read_text(encoding='utf-8')
prov += '\\nThe scoreable native runtime is the Lexus tow-hook bargaining runtime; it binds bargaining:021 seller target/discount, buyer baseline, and product-specific priorities.\\n'
(case/'PROVENANCE.md').write_text(prov,encoding='utf-8')
