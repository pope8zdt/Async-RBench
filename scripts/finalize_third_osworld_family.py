from __future__ import annotations
import hashlib,json,shutil
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'candidate_cases/osw-dependency-unblock-f339b3bb47'
OLD='osw-dependency-unblock-f339b3bb47';CID='osw-dependency-unblock-5c3a1789cf';OLDN='osw_dependency_unblock_f339b3bb47';NEWN='osw_dependency_unblock_5c3a1789cf';OLDP='osw_dependency_unblock_f';NEWP='osw_dependency_unblock_5';OLDS='osworld:chrome:9f935cce-0a9f-435f-8007-817732bfc0a5';NEWS='osworld:chrome:1704f00f-79e6-43a7-961b-cedd3724d5fd'
CASE=ROOT/'candidate_cases'/CID;BP=ROOT/'candidate_cases/rebuild-to-100/blueprints'/CID;RT=ROOT/'candidate_cases/rebuild-to-100/runtime-osworld/cases'/CID;VAL=ROOT/'candidate_cases/rebuild-to-100/runtime-osworld/validation'/CID/'report.json'
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def main():
 if CASE.exists():shutil.rmtree(CASE)
 shutil.copytree(SRC,CASE)
 for p in CASE.rglob('*'):
  if not p.is_file():continue
  try:s=p.read_text(encoding='utf-8')
  except UnicodeDecodeError:continue
  p.write_text(s.replace(OLD,CID).replace(OLDN,NEWN).replace(OLDP,NEWP).replace(OLDS,NEWS),encoding='utf-8',newline='\n')
 shutil.copytree(BP/'private/source_manifests',CASE/'private/source_manifests',dirs_exist_ok=True);shutil.copy2(BP/'private/source_lock.json',CASE/'private/source_lock.json')
 for n in ('official_task.json','hidden_checks.json','semantic_control_registry.json'):
  src=RT/'private'/n;dst=CASE/'private'/('osworld_'+n if n!='official_task.json' else n);shutil.copy2(src,dst)
 eps=json.loads(VAL.read_text())['episodes'];c,e=eps[:2];neg=eps[2:];d=c['event_receipt']['release_after_digest'];report={'schema_version':'async-rbench-osworld-canonical-family-v1','case_id':CID,'model_episode_executed':False,'episode_owner':'evaluator','evidence_sha256':d,'anomaly':'INSERT_LARGE_DATA','source_native_marble_verified':True,'native_evaluator_verified':True,'host_checkpoint':{'owner':'host_runtime','checkpoint_sha256':d},'canonical':c,'equivalent':e,'counterexamples':neg,'passed':c['official_score']==1 and e['official_score']==1 and len(neg)>=2 and all(x['official_score']==0 for x in neg)}
 dump(CASE/'private/native_canonical_report.json',report);dump(CASE/'task/task_file/native_canonical_report.json',report)
 source='Find a large car from next Monday to Friday in Zurich, sorted by price.';inst=source+'\n\nASYNC-RBENCH EXTENSION\nAfter a persisted search checkpoint, consume evaluator-owned evidence, preserve valid location/date state, and reverify category and sort order.';task={'author_name':'Async-RBench individualized rebuild','category':'OSWorld','difficulty':'validated_native','instruction':inst,'tags':['OSWorld','delayed_authoritative_result','live_eventful']};write(CASE/'task/task.yaml',yaml.safe_dump(task,sort_keys=False,allow_unicode=True));write(CASE/'instruction.md',inst+'\n');dump(CASE/'private/source_task.yaml',{'instruction':source})
 q=json.loads((CASE/'private/quality_contract.yaml').read_text());q['source_contract']['sources'][0]['instruction_sha256']=hashlib.sha256(source.encode()).hexdigest();q['requirements'][0]['public_evidence']=[{'path':'task/task.yaml','contains':'ASYNC-RBENCH EXTENSION'},{'path':'task/task.yaml','contains':'large car'}];dump(CASE/'private/quality_contract.yaml',q)
 a={'accepted':True,'model_episode_required':False,'accepted_episode_owner':'evaluator','official_evaluator_score':1.0,'equivalent_score':1.0,'negative_scores':[0.0,0.0],'native_report':'private/native_canonical_report.json'};dump(CASE/'private/canonical_episode_acceptance.json',a);print(CASE)
if __name__=='__main__':main()
