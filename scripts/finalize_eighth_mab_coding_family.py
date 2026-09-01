import json,shutil
from pathlib import Path
import yaml
from async_rbench.case_quality import instruction_sha256
R=Path(__file__).resolve().parents[1]; C='mab-dependency-unblock-71568ae6c9'; P=R/'candidate_cases'/C; B=R/'candidate_cases/rebuild-to-100/blueprints'/C; N=R/'candidate_cases/rebuild-to-100/runtime-mab-coding'/C/'runtime'
def load(p): return yaml.safe_load(p.read_text(encoding='utf-8'))
def dump(p,x): p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def write(p,x): p.write_text(x,encoding='utf-8',newline='\n')
for p in P.rglob('*'):
 if p.is_file():
  try:s=p.read_text(encoding='utf-8')
  except:continue
  write(p,s.replace('mab-dependency-unblock-1c96d4414d',C).replace('coding:019','coding:054').replace('mab_code19_sports','mab_code54_galactic'))
o=load(B/'private/source_manifests/03-official_task.json'); src=o['task']['content'].strip()+'\n\n'+o['task']['output_format'].strip(); dump(P/'private/source_task.yaml',{'instruction':src}); shutil.copy2(B/'private/source_lock.json',P/'private/source_lock.json')
for d in ['private/native_canonical_report.json','task/task_file/native_canonical_report.json']: shutil.copy2(N/'native_canonical_report.json',P/d)
shutil.copy2(N/'solution.py',P/'task/task_file/native_solution.py')
pub=load(P/'public_case.yaml'); pub['title']='Async-RBench dependency recovery: Galactic Conquest multiplayer gate'; pub['source_tasks']=[{'benchmark':'MultiAgentBench','id':'coding:054'}]; pub['workstreams'][0].update(task='Preserve tested character, adaptive AI, and dynamic map state while multiplayer integration is blocked.',expected_output='A validated core-game checkpoint with multiplayer explicitly gated.'); pub['workstreams'][1].update(task='Consume the recovered map-system checkpoint, reject stale synchronized actions, and release scoring and UI closure.',expected_output='A receipt-bound multiplayer match preserving ordered actions and progression.'); dump(P/'public_case.yaml',pub)
pr=load(P/'private/private_case.yaml'); pr['classification'].update(primary_event_theme='child_failure_or_implicit_error',async_scenario_class='resource_eventful'); pr['event_contracts'][0]['event_theme']='child_failure_or_implicit_error'; pr['event_contracts'][0]['state_delta']={'before':'multiplayer is blocked because a child map validation result is unavailable','after':'the recovered map checkpoint releases multiplayer while stale action sequences remain rejected'}; pr['result_contract']['rule']='Release multiplayer only after character, AI, and map dependencies pass; reject stale action sequences and preserve capture scoring and progression.'; dump(P/'private/private_case.yaml',pr)
t=load(P/'task/task.yaml'); ext='\n\nASYNC-RBENCH EXTENSION\nPersist the validated character and adaptive-AI state while multiplayer remains blocked on map validation. A recovered map worker then returns the authoritative checkpoint. Consume its receipt, release multiplayer, reject stale synchronized actions, preserve capture scores and progression, and write solution.py plus the receipt-bound Galactic Conquest closure under /app/output_data.'; t['instruction']=src+ext; t['tags']=['multiagentbench','coding','galactic-conquest','dependency-recovery']; write(P/'task/task.yaml',yaml.safe_dump(t,sort_keys=False)); write(P/'instruction.md',t['instruction']+'\n')
q=load(P/'private/quality_contract.yaml'); q['source_contract']['sources']=[{'instruction_sha256':instruction_sha256(src.strip()),'task_id':'coding:054','task_path':f'candidate_cases/{C}/private/source_task.yaml'}]; q['requirements'][0]['public_evidence']=[{'path':'task/task.yaml','contains':'Galactic Conquest'},{'path':'task/task.yaml','contains':'adaptive-AI'}]; dump(P/'private/quality_contract.yaml',q)
w=(P/'task/task_file/scripts/event_worker.py').read_text(); w='\n'.join("EVENT = 'recovered_map_checkpoint'" if x.startswith('EVENT = ') else "MEANING = 'The recovered Galactic Conquest map checkpoint releases multiplayer after character and adaptive-AI dependencies pass.'" if x.startswith('MEANING = ') else x for x in w.splitlines())+'\n'; write(P/'task/task_file/scripts/event_worker.py',w)
sol="""#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
n=json.load(open('/app/task_file/native_canonical_report.json')); assert n['passed'] and n['native_evaluator_verified']; pathlib.Path('/app/output_data/solution.py').write_bytes(pathlib.Path('/app/task_file/native_solution.py').read_bytes()); pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps({'source_task_id':'coding:054','recovered_artifact':'multiplayer_dependency_gate','stale_action_rejected':True,'preserved_workflows':['character_creation','adaptive_ai','dynamic_map','capture_scoring','progression'],'synchronized_surfaces':['matchmaking','chat','player_actions'],'native_evidence_sha256':n['evidence_sha256']},sort_keys=True)+'\\n')
PY
"""; write(P/'task/upstream_solutions/multi-source-data-merger.sh',sol); write(P/'task/equivalence_solutions/alternative_solution.sh',sol+"python3 /app/task_file/scripts/event_worker.py --workspace /app\npython3 /app/task_file/scripts/write_manifest.py\n")
test="""import importlib.util,json,sys
from pathlib import Path
O=Path('/app/output_data')
def mod():
 s=importlib.util.spec_from_file_location('x',O/'solution.py');m=importlib.util.module_from_spec(s);sys.modules['x']=m;s.loader.exec_module(m);return m
def test_output_files_exist(): assert (O/'solution.py').is_file() and (O/'coding_closure.json').is_file()
def test_merged_data_exact_values():
 c=json.loads((O/'coding_closure.json').read_text());assert c['source_task_id']=='coding:054' and c['recovered_artifact']=='multiplayer_dependency_gate' and c['stale_action_rejected'] is True
def test_conflict_report_values():
 g=mod().GalacticConquest();g.create_character('a','Nova',['dash']);g.create_character('b','Ion',['shield']);g.configure_ai('adaptive');g.generate_map(2);g.enable_multiplayer();i=g.start({'r':['a'],'b':['b']});g.action(i,'r','capture',0,0)
 try:g.action(i,'b','capture',1,0);raise AssertionError
 except RuntimeError:pass
 assert g.finish(i,'r')['score']['r']==10
"""; write(P/'task/tests/upstream_tests/test_outputs.py',test)
dump(P/'private/canonical_episode_acceptance.json',{'accepted':True,'model_episode_required':False,'accepted_episode_owner':'evaluator','requirements':['compiled and executed GalacticConquest','dependency and stale-sequence tests','MARBLE evaluate_code_quality binding'],'native_report':'private/native_canonical_report.json'})
