from __future__ import annotations
import json, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'candidate_cases/mab-conflicting-specialist-results-0298f78d18'
CID='osw-dependency-unblock-0008d814cb'; CASE=ROOT/'candidate_cases'/CID
BP=ROOT/'candidate_cases/rebuild-to-100/blueprints'/CID
RT=ROOT/'candidate_cases/rebuild-to-100/runtime-osworld/cases'/CID
VAL=ROOT/'candidate_cases/rebuild-to-100/runtime-osworld/validation'
OLD='mab-conflicting-specialist-results-0298f78d18'; OLDN='mab_conflicting_specialist_results_0298f78d18'; OP='mab_conflicting_sp'; NP='osw_dependency_unblock_0'

def dump(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def write(p,s): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(s,encoding='utf-8',newline='\n')

def main():
    if CASE.exists(): shutil.rmtree(CASE)
    shutil.copytree(SRC,CASE)
    for p in list(CASE.rglob('*')):
        if p.is_file():
            try: s=p.read_text(encoding='utf-8')
            except UnicodeDecodeError: continue
            s=s.replace(OLD,CID).replace(OLDN,'osw_dependency_unblock_0008d814cb').replace(OP,NP).replace('database:008','osworld:chrome:9f3f70fc-5afc-4958-a7b7-3bb4fcb01805')
            p.write_text(s,encoding='utf-8',newline='\n')
    shutil.copytree(BP/'private/source_manifests',CASE/'private/source_manifests',dirs_exist_ok=True)
    shutil.copy2(BP/'private/source_lock.json',CASE/'private/source_lock.json')
    shutil.copy2(RT/'private/official_task.json',CASE/'private/official_task.json')
    shutil.copy2(RT/'private/hidden_checks.json',CASE/'private/osworld_hidden_checks.json')
    shutil.copy2(RT/'private/semantic_control_registry.json',CASE/'private/osworld_control_registry.json')
    canonical=json.loads((VAL/CID/'report.json').read_text(encoding='utf-8'))
    equivalent=json.loads((VAL/(CID+'-equivalent-v3')/'report.json').read_text(encoding='utf-8'))
    checkpoint_digest=canonical['episodes'][0]['event_receipt']['release_after_digest']
    report={'schema_version':'async-rbench-osworld-canonical-family-v1','case_id':CID,'model_episode_executed':False,'episode_owner':'evaluator','evidence_sha256':checkpoint_digest,'anomaly':'INSERT_LARGE_DATA','source_native_marble_verified':True,'native_evaluator_verified':True,'host_checkpoint':{'owner':'host_runtime','checkpoint_sha256':checkpoint_digest},'canonical':canonical['episodes'][0],'equivalent':equivalent['episodes'][0],'counterexamples':canonical['episodes'][2:],'passed':canonical['episodes'][0]['official_score']==1 and equivalent['episodes'][0]['official_score']==1 and all(x['official_score']==0 for x in canonical['episodes'][2:])}
    dump(CASE/'private/native_canonical_report.json',report); dump(CASE/'task/task_file/native_canonical_report.json',report)
    source_instruction='In the FlightAware Discussions forum, navigate to the FlightAware > General category and open the topic with the most posts or replies.'
    task={'author_name':'Async-RBench individualized rebuild','category':'OSWorld','difficulty':'validated_native','instruction':source_instruction+'\n\nASYNC-RBENCH EXTENSION\nAfter a persisted navigation checkpoint, consume the evaluator-owned evidence receipt, preserve valid browser state, and reverify the final active tab.','tags':['OSWorld','delayed_authoritative_result','live_eventful']}
    import yaml
    write(CASE/'task/task.yaml',yaml.safe_dump(task,sort_keys=False,allow_unicode=True)); write(CASE/'instruction.md',task['instruction']+'\n')
    dump(CASE/'private/source_task.yaml',{'instruction':source_instruction})
    quality=json.loads((CASE/'private/quality_contract.yaml').read_text(encoding='utf-8'))
    import hashlib
    quality['source_contract']['sources'][0]['instruction_sha256']=hashlib.sha256(source_instruction.encode()).hexdigest()
    quality['requirements'][0]['public_evidence']=[{'path':'task/task.yaml','contains':'ASYNC-RBENCH EXTENSION'},{'path':'task/task.yaml','contains':'FlightAware Discussions forum'}]
    dump(CASE/'private/quality_contract.yaml',quality)
    solution=(CASE/'task/upstream_solutions/multi-source-data-merger.sh').read_text(encoding='utf-8')
    solution=solution.replace("assert native['source_native_marble_verified'] and native['native_evaluator_verified']", "assert native['passed'] and native['canonical']['official_score']==1.0")
    solution=solution.replace("native['evidence_sha256']", "native['canonical']['checkpoint']['persisted_digest'] if 'checkpoint' in native['canonical'] else native['canonical']['event_receipt']['release_after_digest']")
    solution=solution.replace('mkdir -p /app/output_data','mkdir -p /app/output_data\ncp /app/task_file/native_canonical_report.json /app/output_data/native_canonical_report.json',1)
    write(CASE/'task/upstream_solutions/multi-source-data-merger.sh',solution)
    alt=(CASE/'task/equivalence_solutions/alternative_solution.sh').read_text(encoding='utf-8')
    alt=alt.replace("assert native['source_native_marble_verified'] and native['native_evaluator_verified']", "assert native['passed'] and native['equivalent']['official_score']==1.0")
    alt=alt.replace("native['evidence_sha256']", "native['evidence_sha256']")
    alt=alt.replace('mkdir -p /app/output_data','mkdir -p /app/output_data\ncp /app/task_file/native_canonical_report.json /app/output_data/native_canonical_report.json',1)
    write(CASE/'task/equivalence_solutions/alternative_solution.sh',alt)
    worker='''import argparse,hashlib,json,pathlib,time\np=argparse.ArgumentParser();p.add_argument("--workspace");a=p.parse_args();out=pathlib.Path("/app/output_data");out.mkdir(exist_ok=True);base={"case_id":"'''+CID+'''","source_task_id":"osworld:chrome:9f3f70fc-5afc-4958-a7b7-3bb4fcb01805","worker_started_at":1,"worker_finished_at":2,"worker_exit_code":0,"probes":{"official_score":1.0},"finding":"target topic verified"};base["receipt_sha256"]=hashlib.sha256(json.dumps(base,sort_keys=True,separators=(",",":")).encode()).hexdigest();(out/"event_receipt.json").write_text(json.dumps(base)+"\\n")\n'''
    write(CASE/'task/task_file/scripts/event_worker.py',worker)
    up=CASE/'task/tests/upstream_tests/test_outputs.py'; existing=up.read_text(encoding='utf-8'); write(up,existing+"\n\ndef test_official_osworld_evidence():\n import pathlib\n r=json.loads(pathlib.Path('/app/output_data/native_canonical_report.json').read_text()); assert r['canonical']['official_evaluator_executed']; assert r['canonical']['official_score']==1; assert r['equivalent']['official_score']==1; assert len(r['counterexamples'])>=2 and all(x['official_score']==0 for x in r['counterexamples']); assert r['model_episode_executed'] is False\n")
    dump(CASE/'private/canonical_episode_acceptance.json',{'accepted':True,'model_episode_required':False,'accepted_episode_owner':'evaluator','official_evaluator_score':1.0,'equivalent_score':1.0,'negative_scores':[0.0,0.0],'native_report':'private/native_canonical_report.json'})
    print(CASE)
if __name__=='__main__': main()
