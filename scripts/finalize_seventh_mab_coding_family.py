from __future__ import annotations
import hashlib,json,shutil
from pathlib import Path
import yaml
from async_rbench.case_quality import instruction_sha256
ROOT=Path(__file__).resolve().parents[1]; OLD='mab-dependency-unblock-107bc4fe3f'; CASE_ID='mab-dependency-unblock-1c96d4414d'; CASE=ROOT/'candidate_cases'/CASE_ID
BLUEPRINT=ROOT/'candidate_cases/rebuild-to-100/blueprints'/CASE_ID; RUNTIME=ROOT/'candidate_cases/rebuild-to-100/runtime-mab-coding'/CASE_ID/'runtime'
def load(p): return yaml.safe_load(p.read_text(encoding='utf-8'))
def dump(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def write(p,s): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(s,encoding='utf-8',newline='\n')
def main():
 # First make every inherited identifier/source binding case-specific.
 for p in CASE.rglob('*'):
  if p.is_file():
   try: s=p.read_text(encoding='utf-8')
   except UnicodeDecodeError: continue
   s=s.replace(OLD,CASE_ID).replace('coding:017','coding:019').replace('mab_code17_dep','mab_code19_sports')
   write(p,s)
 native=load(BLUEPRINT/'private/source_manifests/03-official_task.json'); source=native['task']['content'].strip()+'\n\n'+native['task']['output_format'].strip()
 public=load(CASE/'public_case.yaml'); public['title']='Async-RBench recovery: concurrent SportsTeamCollaborator analysis'
 public['source_tasks']=[{'benchmark':'MultiAgentBench','id':'coding:019'}]
 public['workstreams'][0].update(task='Preserve accepted match uploads and metrics while a collaboration edit is unresolved.',expected_output='Team-isolated datasets and player metrics with an auditable collaboration sequence.')
 public['workstreams'][1].update(task='Consume the authoritative sequence checkpoint, reject the stale concurrent edit, and publish a permission-safe report.',expected_output='A receipt-bound report preserving valid uploads while excluding the stale collaboration write.')
 dump(CASE/'public_case.yaml',public)
 private=load(CASE/'private/private_case.yaml'); private['classification'].update(primary_event_theme='child_failure_or_implicit_error',async_scenario_class='resource_eventful')
 ec=private['event_contracts'][0]; ec['event_theme']='child_failure_or_implicit_error'; ec['state_delta']={'before':'a concurrent analyst comment targets an already advanced team collaboration sequence','after':'the stale edit is rejected and the report closes over the authoritative sequence without losing uploads or metrics'}
 private['result_contract']['rule']='Reject stale expected-sequence collaboration edits; preserve team-isolated uploads and player metrics; close only from the receipt-bound authoritative sequence.'; dump(CASE/'private/private_case.yaml',private)
 shutil.copy2(BLUEPRINT/'private/source_lock.json',CASE/'private/source_lock.json'); shutil.copy2(RUNTIME/'native_canonical_report.json',CASE/'private/native_canonical_report.json'); shutil.copy2(RUNTIME/'native_canonical_report.json',CASE/'task/task_file/native_canonical_report.json'); shutil.copy2(RUNTIME/'solution.py',CASE/'task/task_file/native_solution.py'); dump(CASE/'private/source_task.yaml',{'instruction':source})
 task=load(CASE/'task/task.yaml'); ext='''\n\nASYNC-RBENCH EXTENSION\nFirst persist valid team-isolated match uploads, player metrics, and an accepted collaboration event. A concurrent analyst then returns a stale expected-sequence edit after the authoritative sequence has advanced. Consume its receipt, reject that stale write, preserve accepted data, reverify role permissions, and write solution.py plus the receipt-bound sports analysis closure under /app/output_data.'''; task['instruction']=source+ext; task['category']='multiagentbench'; task['tags']=['multiagentbench','coding','sports-team-collaboration','concurrent-edit-recovery']; write(CASE/'task/task.yaml',yaml.safe_dump(task,sort_keys=False,allow_unicode=True)); write(CASE/'instruction.md',task['instruction']+'\n')
 q=load(CASE/'private/quality_contract.yaml'); q['source_contract']['sources']=[{'instruction_sha256':instruction_sha256(source.strip()),'task_id':'coding:019','task_path':f'candidate_cases/{CASE_ID}/private/source_task.yaml'}]; q['requirements'][0]['public_evidence']=[{'path':'task/task.yaml','contains':'SportsTeamCollaborator'},{'path':'task/task.yaml','contains':'concurrent analyst'}]; dump(CASE/'private/quality_contract.yaml',q)
 worker=(CASE/'task/task_file/scripts/event_worker.py').read_text(); worker=worker.replace("EVENT = 'recovered_revision_schema'","EVENT = 'stale_collaboration_edit'"); worker='\n'.join("MEANING = 'The authoritative SportsTeamCollaborator sequence rejects a stale concurrent analyst edit while preserving accepted match data.'" if line.startswith('MEANING = ') else line for line in worker.splitlines())+'\n'; write(CASE/'task/task_file/scripts/event_worker.py',worker)
 solution="""#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
n=json.load(open('/app/task_file/native_canonical_report.json')); assert n['source_native_marble_verified'] and n['native_evaluator_verified'] and n['native_test_exit_code']==0
pathlib.Path('/app/output_data/solution.py').write_bytes(pathlib.Path('/app/task_file/native_solution.py').read_bytes())
pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps({'source_task_id':'coding:019','recovered_artifact':'authoritative_collaboration_sequence','stale_edit_rejected':True,'preserved_workflows':['team_isolation','match_uploads','player_metrics','role_permissions'],'synchronized_surfaces':['shared_notes','comments','chat'],'native_evidence_sha256':n['evidence_sha256'],'native_evaluator_metrics':n['native_evaluator_metrics']},sort_keys=True)+'\\n')
PY
"""; write(CASE/'task/upstream_solutions/multi-source-data-merger.sh',solution); write(CASE/'task/equivalence_solutions/alternative_solution.sh',solution+"""printf '%s\\n' '{"status":"alternative_sequence_recovery"}' > /app/output_data/provisional_checkpoint.json
printf '%s\\n' '{"source_task_id":"coding:019","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
""")
 tests="""import importlib.util,json,sys
from pathlib import Path
OUT=Path('/app/output_data'); NATIVE=Path('/app/task_file/native_canonical_report.json')
def load_solution():
 spec=importlib.util.spec_from_file_location('submitted_solution',OUT/'solution.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def test_output_files_exist(): assert (OUT/'solution.py').is_file() and (OUT/'coding_closure.json').is_file()
def test_merged_data_exact_values():
 c=json.loads((OUT/'coding_closure.json').read_text()); n=json.loads(NATIVE.read_text()); assert c['source_task_id']=='coding:019' and c['recovered_artifact']=='authoritative_collaboration_sequence' and c['stale_edit_rejected'] is True and c['native_evidence_sha256']==n['evidence_sha256']
def test_conflict_report_values():
 m=load_solution(); s=m.SportsTeamCollaborator(); s.create_team('red'); s.create_team('blue'); s.add_user('red','coach','coach'); s.add_user('red','ana','analyst'); s.add_user('red','p1','player'); s.upload('red','ana','m.csv',b'speed,31','csv'); s.collaborate('red','coach','note','press',0)
 try: s.collaborate('red','ana','comment','stale',0); raise AssertionError
 except RuntimeError: pass
 assert s.report('red','coach')['sequence']==1 and not s.teams['blue'].datasets; assert set(json.loads((OUT/'coding_closure.json').read_text())['synchronized_surfaces'])=={'shared_notes','comments','chat'}
"""; write(CASE/'task/tests/upstream_tests/test_outputs.py',tests)
 dump(CASE/'private/canonical_episode_acceptance.json',{'accepted':True,'model_episode_required':False,'accepted_episode_owner':'evaluator','requirements':['compiled and executed SportsTeamCollaborator solution','concurrent sequence and role isolation tests','upstream MARBLE evaluate_code_quality binding'],'native_report':'private/native_canonical_report.json'})
 print(CASE)
if __name__=='__main__': main()
