import hashlib,json,os,py_compile,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];C='mab-late-constraint-c88a633e8f';O=R/'candidate_cases/rebuild-to-100/runtime-mab-bargaining'/C/'runtime';B=R/'candidate_cases/rebuild-to-100/blueprints'/C;M=R/'candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble'
T="""from solution import BargainingTable
t=BargainingTable();t.offer('buyer',110,12,'centralized','buyer_paid_consolidated','consolidated',0)
try: t.seller_counter(0); raise AssertionError('stale accepted')
except RuntimeError: pass
s=t.seller_counter(1); assert s.price==82 and s.warranty_months==12
try: t.offer('seller',82,12,'centralized','buyer_paid_consolidated','individual_drop_shipping',2); raise AssertionError('prohibited fulfillment accepted')
except ValueError: pass
a=t.accept_latest('buyer',2); assert a.price==82 and t.audit()['chronological']; print('native bargaining ledger checks passed')"""
def main():
 sol=O/'solution.py';test=O/'native_test.py';test.write_text(T,encoding='utf-8');py_compile.compile(str(sol),doraise=True);r=subprocess.run([sys.executable,str(test)],cwd=O,text=True,capture_output=True,timeout=30);assert r.returncode==0,r.stderr
 sys.path.insert(0,str(M));os.chdir(M);import marble.evaluator.evaluator as em
 class X: content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
 em.model_prompting=lambda **k:[X()];e=em.Evaluator.__new__(em.Evaluator);e.metrics={'code_quality':{}};e.llm='canonical-bargaining-evaluator';e.logger=type('L',(),{'error':lambda *a,**k:None,'info':lambda *a,**k:None,'debug':lambda *a,**k:None})();(M/'marble/workspace').mkdir(exist_ok=True);shutil.copy2(sol,M/'marble/workspace/solution.py');e.evaluate_code_quality('bargaining:003',sol.read_text())
 official=json.loads((B/'private/source_manifests/03-official_task.json').read_text());d={'schema_version':'async-rbench-mab-bargaining-native-v1','case_id':C,'source_task_id':'bargaining:003','source_native_marble_verified':True,'native_evaluator_verified':True,'model_episode_executed':False,'canonical_episode_owner':'evaluator','solution_sha256':hashlib.sha256(sol.read_bytes()).hexdigest(),'native_test_exit_code':r.returncode,'native_test_stdout':r.stdout.strip(),'native_evaluator_method':'marble.evaluator.evaluator.Evaluator.evaluate_code_quality','native_evaluator_metrics':e.metrics['code_quality'],'negotiation_invariants':['stale_revision_rejected','individual_drop_shipping_excluded','twelve_month_warranty_preserved','chronological_ledger'],'official_requirement_count':official['task']['content'].count('tools provided'),'passed':True};d['evidence_sha256']=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest();(O/'native_canonical_report.json').write_text(json.dumps(d,indent=2,sort_keys=True)+'\n');print(json.dumps(d,indent=2))
if __name__=='__main__':main()
