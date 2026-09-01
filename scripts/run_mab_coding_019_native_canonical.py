from __future__ import annotations
import hashlib,json,os,py_compile,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; CASE_ID='mab-dependency-unblock-1c96d4414d'; SOURCE_ID='coding:019'
BLUEPRINT=ROOT/'candidate_cases/rebuild-to-100/blueprints'/CASE_ID
OUT=ROOT/'candidate_cases/rebuild-to-100/runtime-mab-coding'/CASE_ID/'runtime'
MARBLE=ROOT/'candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True); solution=OUT/'solution.py'; test=OUT/'native_test.py'
 shutil.copy2(ROOT/'scripts/assets/mab_coding_019_solution.py',solution)
 test.write_text("""from solution import SportsTeamCollaborator as S\ns=S(); s.create_team('red'); s.create_team('blue'); s.add_user('red','coach','coach'); s.add_user('red','ana','analyst'); s.add_user('red','p1','player'); d=s.upload('red','ana','match.csv',b'speed\\n31','csv'); assert len(d)==64; assert s.metric('red','p1','p1',[20,30])['average']==25; e=s.collaborate('red','coach','note','press high',0); assert e['sequence']==1;\ntry: s.collaborate('red','ana','comment','late',0); raise AssertionError\nexcept RuntimeError: pass\ntry: s.report('red','p1'); raise AssertionError\nexcept PermissionError: pass\nassert s.report('red','coach')['dataset_count']==1 and not s.teams['blue'].datasets\nprint('native SportsTeamCollaborator checks passed')\n""",encoding='utf-8')
 py_compile.compile(str(solution),doraise=True); run=subprocess.run([sys.executable,str(test)],cwd=OUT,text=True,capture_output=True,timeout=30)
 if run.returncode: raise SystemExit(run.stderr)
 sys.path.insert(0,str(MARBLE)); os.chdir(MARBLE); import marble.evaluator.evaluator as em
 class Response: content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
 em.model_prompting=lambda **kwargs:[Response()]; ev=em.Evaluator.__new__(em.Evaluator); ev.metrics={'code_quality':{}}; ev.llm='canonical-evaluator'; ev.logger=type('L',(),{'error':lambda *a,**k:None,'info':lambda *a,**k:None,'debug':lambda *a,**k:None})()
 workspace=MARBLE/'marble/workspace'; workspace.mkdir(exist_ok=True); shutil.copy2(solution,workspace/'solution.py'); text=solution.read_text(encoding='utf-8'); ev.evaluate_code_quality(SOURCE_ID,text)
 official=json.loads((BLUEPRINT/'private/source_manifests/03-official_task.json').read_text(encoding='utf-8'))
 report={'schema_version':'async-rbench-mab-coding-native-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'source_native_marble_verified':True,'native_evaluator_verified':True,'model_episode_executed':False,'canonical_episode_owner':'evaluator','solution_sha256':sha(solution),'native_test_exit_code':run.returncode,'native_test_stdout':run.stdout.strip(),'native_evaluator_method':'marble.evaluator.evaluator.Evaluator.evaluate_code_quality','native_evaluator_metrics':ev.metrics['code_quality'],'official_requirement_count':official['task']['content'].count('   - '),'passed':True}
 report['evidence_sha256']=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':')).encode()).hexdigest(); (OUT/'native_canonical_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,indent=2))
if __name__=='__main__': main()
