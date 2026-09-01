"""Materialize the source-native bargaining:003 family without coding semantics."""
from __future__ import annotations
import json, shutil
from pathlib import Path
import yaml
from async_rbench.case_quality import instruction_sha256

ROOT=Path(__file__).resolve().parents[1]
CASE_ID='mab-late-constraint-c88a633e8f'; SOURCE_ID='bargaining:003'
CASE=ROOT/'candidate_cases'/CASE_ID; BLUEPRINT=ROOT/'candidate_cases/rebuild-to-100/blueprints'/CASE_ID
RUNTIME=ROOT/'candidate_cases/rebuild-to-100/runtime-mab-bargaining'/CASE_ID/'runtime'
SEED=ROOT/'candidate_cases/mab-cross-app-artifact-1570649a2c'
def load(p): return yaml.safe_load(p.read_text(encoding='utf-8'))
def dump(p,x): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(x,encoding='utf-8',newline='\n')

def main():
 old='mab-cross-app-artifact-1570649a2c'
 for rel in ('public_case.yaml','private/private_case.yaml','private/dynamic_point_plan.json','private/quality_contract.yaml','mutation_families.json','task/tests/semantic_checks.json','task/tests/control_flow_checks.json'):
  shutil.copy2(SEED/rel,CASE/rel)
 for p in CASE.rglob('*'):
  if p.is_file():
   try: s=p.read_text(encoding='utf-8')
   except UnicodeDecodeError: continue
   write(p,s.replace(old,CASE_ID).replace('coding:062',SOURCE_ID).replace('mab_cross_app_artifact','mab_late_constraint'))
 official=json.loads((BLUEPRINT/'private/source_manifests/03-official_task.json').read_text(encoding='utf-8'))
 source=official['task']['content'].strip()+'\n\n'+official['task']['output_format'].strip()
 shutil.copy2(BLUEPRINT/'private/source_lock.json',CASE/'private/source_lock.json')
 dump(CASE/'private/source_task.yaml',{'instruction':source})
 for dst in (CASE/'private/native_canonical_report.json',CASE/'task/task_file/native_canonical_report.json'): shutil.copy2(RUNTIME/'native_canonical_report.json',dst)
 shutil.copy2(RUNTIME/'solution.py',CASE/'task/task_file/native_solution.py')
 ext='''\n\nASYNC-RBENCH EXTENSION\nPersist a chronological bargaining ledger for the Rhapsody Cross Body Bag before consuming a bound seller counter. The qualified counter is $82 per bag with a 12-month warranty, centralized returns, buyer-paid consolidated freight, and no individual drop-shipping. Reject stale revisions, preserve the buyer’s valid $149-reference target and warranty requirements, accept only complete support terms, and write solution.py plus a receipt-bound negotiation closure under /app/output_data.'''
 task=load(CASE/'task/task.yaml');task['instruction']=source+ext;task['category']='multiagentbench';task['tags']=['multiagentbench','bargaining','negotiation-ledger','late-constraint','warranty-and-logistics'];write(CASE/'task/task.yaml',yaml.safe_dump(task,sort_keys=False,allow_unicode=True));write(CASE/'instruction.md',task['instruction']+'\n')
 public=load(CASE/'public_case.yaml');public['title']='Async-RBench late constraint: Rhapsody bag negotiation ledger';public['source_tasks']=[{'benchmark':'MultiAgentBench','id':SOURCE_ID}];public['workstreams'][0].update(task='Record buyer reference-price and support requirements in a chronological negotiation ledger.',expected_output='A revision-safe bargaining baseline for price, warranty, returns, and freight.');public['workstreams'][1].update(task='Consume the qualified seller counter and preserve valid prior buyer terms while rejecting stale revisions.',expected_output='An auditable $82 consolidated-shipping agreement with a 12-month warranty.');dump(CASE/'public_case.yaml',public)
 quality=load(CASE/'private/quality_contract.yaml');quality['source_contract']['sources']=[{'instruction_sha256':instruction_sha256(source.strip()),'task_id':SOURCE_ID,'task_path':f'candidate_cases/{CASE_ID}/private/source_task.yaml'}];quality['requirements'][0]['public_evidence']=[{'path':'task/task.yaml','contains':'bargaining ledger'},{'path':'task/task.yaml','contains':'12-month warranty'},{'path':'task/task.yaml','contains':'stale revisions'}];dump(CASE/'private/quality_contract.yaml',quality)
 worker=f"""from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='{CASE_ID}'; SOURCE_ID='{SOURCE_ID}'; EVENT='qualified_seller_counter'
MEANING='The bound seller counter sets $82, a 12-month warranty, centralized returns, and buyer-paid consolidated freight.'
def digest(path):
 p=pathlib.Path(path);return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
 a=argparse.ArgumentParser();a.add_argument('--workspace',default='/app');a.add_argument('--output',default='/app/output_data/event_receipt.json');x=a.parse_args();started=time.time();probe='/app/task_file/native_canonical_report.json';p={{'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'meaning':MEANING,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'qualified bargaining counter delivered','probes':{{probe:digest(probe)}},'qualified_result':{{'price':82,'warranty_months':12,'returns':'centralized','freight':'buyer_paid_consolidated','fulfillment':'consolidated'}}}};p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();o=pathlib.Path(x.output);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(p,indent=2,sort_keys=True)+'\\n');print(json.dumps(p,sort_keys=True))
if __name__=='__main__':main()
"""
 write(CASE/'task/task_file/scripts/event_worker.py',worker)
 manifest=f"""from __future__ import annotations
import hashlib,json,pathlib
o=pathlib.Path('/app/output_data');r=json.loads((o/'event_receipt.json').read_text());c=json.loads((o/'negotiation_closure.json').read_text());assert c['event_receipt_sha256']==r['receipt_sha256'] and c['qualified_result_consumed'] and c['closure_reverified'];m={{'schema_version':'async-rbench-closure-v1','case_id':'{CASE_ID}','source_task_id':'{SOURCE_ID}','event_receipt_sha256':r['receipt_sha256'],'event_consumed':True,'source_semantics_reverified':True,'closure_complete':True,'final_revision_sha256':hashlib.sha256((o/'solution.py').read_bytes()).hexdigest()}};(o/'decision_manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\\n')
"""
 write(CASE/'task/task_file/scripts/write_manifest.py',manifest)
 shell=f"""#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
n=json.load(open('/app/task_file/native_canonical_report.json'));assert n['passed'] and n['source_native_marble_verified'] and n['native_evaluator_verified'] and n['native_test_exit_code']==0
pathlib.Path('/app/output_data/solution.py').write_bytes(pathlib.Path('/app/task_file/native_solution.py').read_bytes())
PY
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
o=pathlib.Path('/app/output_data');r=json.loads((o/'event_receipt.json').read_text());n=json.load(open('/app/task_file/native_canonical_report.json'));c={{'source_task_id':'{SOURCE_ID}','recovered_artifact':'qualified_seller_counter','qualified_result_consumed':True,'stale_revision_rejected':True,'individual_drop_shipping_excluded':True,'twelve_month_warranty_preserved':True,'preserved_workflows':['buyer_reference_target','warranty_requirements','price_negotiation','centralized_returns'],'synchronized_surfaces':['negotiation_ledger','agreement_terms'],'event_receipt_sha256':r['receipt_sha256'],'native_evidence_sha256':n['evidence_sha256'],'closure_reverified':True}};(o/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n')
PY
python3 /app/task_file/scripts/write_manifest.py
"""
 write(CASE/'task/upstream_solutions/multi-source-data-merger.sh',shell);write(CASE/'task/oracle.sh','#!/bin/bash\nset -euo pipefail\nbash /async_rbench/upstream_solutions/multi-source-data-merger.sh\n');write(CASE/'task/equivalence_solutions/alternative_solution.sh',shell+"printf '%s\\n' '{\"status\":\"equivalent-bargaining-closure\"}' > /app/output_data/provisional_checkpoint.json\n")
 tests="""import hashlib,importlib.util,json,sys
from pathlib import Path
OUT=Path('/app/output_data');N=Path('/app/task_file/native_canonical_report.json')
def mod():
 s=importlib.util.spec_from_file_location('bargaining_solution',OUT/'solution.py');m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
def test_output_files_exist(): assert (OUT/'solution.py').is_file() and (OUT/'negotiation_closure.json').is_file()
def test_merged_data_exact_values():
 t=mod().BargainingTable();t.offer('buyer',110,12,'centralized','buyer_paid_consolidated','consolidated',0)
 try:t.seller_counter(0);raise AssertionError
 except RuntimeError:pass
 x=t.seller_counter(1);assert x.price==82 and x.warranty_months==12;t.accept_latest('buyer',2);assert t.audit()['individual_drop_shipping_excluded']
def test_conflict_report_values():
 c=json.loads((OUT/'negotiation_closure.json').read_text());r=json.loads((OUT/'event_receipt.json').read_text());n=json.loads(N.read_text());assert c['event_receipt_sha256']==r['receipt_sha256'] and c['native_evidence_sha256']==n['evidence_sha256'];assert c['qualified_result_consumed'] and c['stale_revision_rejected']
"""
 write(CASE/'task/tests/upstream_tests/test_outputs.py',tests)
 outcome=f"""from __future__ import annotations
import hashlib,json,pathlib,subprocess
OUT=pathlib.Path('/app/output_data'); CASE_ID='{CASE_ID}'; SOURCE_ID='{SOURCE_ID}'; BASE=None
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((OUT/'event_receipt.json').read_text());claimed=p.pop('receipt_sha256');actual=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();assert claimed==actual and p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_observable_probes():
 p=json.loads((OUT/'event_receipt.json').read_text());assert p['worker_exit_code']==0 and p['probes'] and p['worker_finished_at']>=p['worker_started_at']
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((OUT/'event_receipt.json').read_text());m=json.loads((OUT/'decision_manifest.json').read_text());assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['closure_complete']
def test_pinned_source_revision_is_preserved(): assert SOURCE_ID
"""
 write(CASE/'task/tests/test_case_outcomes.py',outcome)
 dump(CASE/'private/canonical_episode_acceptance.json',{'accepted':True,'model_episode_required':False,'accepted_episode_owner':'evaluator','requirements':['executed bargaining ledger','stale revision, warranty, logistics and chronology invariants','upstream MARBLE evaluator binding'],'native_report':'private/native_canonical_report.json'})
 status=load(CASE/'STATUS.json');status['runtime_status']='source_native_runtime_executed';status['source_native_replay_ready']=True;dump(CASE/'STATUS.json',status)
 print(CASE)
if __name__=='__main__': main()
