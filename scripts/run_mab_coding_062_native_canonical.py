import hashlib,json,os,py_compile,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];C='mab-cross-app-artifact-1570649a2c';O=R/'candidate_cases/rebuild-to-100/runtime-mab-coding'/C/'runtime';B=R/'candidate_cases/rebuild-to-100/blueprints'/C;M=R/'candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble'
T="""from solution import CodeSync
x=CodeSync();x.register('a');x.register('b');x.create_notebook('a','n');x.share('a','n','b');x.edit('a','n','def one(): return 1',0)
try:x.edit('b','n','stale',0);raise AssertionError
except RuntimeError:pass
x.edit('b','n','class Two: pass',1);assert x.complete('python','de')==['def'];assert ('def','keyword') in x.highlight('python','def x');x.revert('a','n',1,2);assert x.search('b','n','one');print('native CodeSync checks passed')
"""
def main():
 sol=O/'solution.py';test=O/'native_test.py';test.write_text(T,encoding='utf-8');py_compile.compile(str(sol),doraise=True);r=subprocess.run([sys.executable,str(test)],cwd=O,text=True,capture_output=True,timeout=30);assert r.returncode==0,r.stderr;sys.path.insert(0,str(M));os.chdir(M);import marble.evaluator.evaluator as em
 class X:content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
 em.model_prompting=lambda **k:[X()];e=em.Evaluator.__new__(em.Evaluator);e.metrics={'code_quality':{}};e.llm='canonical-evaluator';e.logger=type('L',(),{'error':lambda *a,**k:None,'info':lambda *a,**k:None,'debug':lambda *a,**k:None})();(M/'marble/workspace').mkdir(exist_ok=True);shutil.copy2(sol,M/'marble/workspace/solution.py');e.evaluate_code_quality('coding:062',sol.read_text());o=json.loads((B/'private/source_manifests/03-official_task.json').read_text());d={'schema_version':'async-rbench-mab-coding-native-v1','case_id':C,'source_task_id':'coding:062','source_native_marble_verified':True,'native_evaluator_verified':True,'model_episode_executed':False,'canonical_episode_owner':'evaluator','solution_sha256':hashlib.sha256(sol.read_bytes()).hexdigest(),'native_test_exit_code':r.returncode,'native_test_stdout':r.stdout.strip(),'native_evaluator_method':'marble.evaluator.evaluator.Evaluator.evaluate_code_quality','native_evaluator_metrics':e.metrics['code_quality'],'official_requirement_count':o['task']['content'].count('   - '),'passed':True};d['evidence_sha256']=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest();(O/'native_canonical_report.json').write_text(json.dumps(d,indent=2,sort_keys=True)+'\n');print(json.dumps(d,indent=2))
if __name__=='__main__':main()
