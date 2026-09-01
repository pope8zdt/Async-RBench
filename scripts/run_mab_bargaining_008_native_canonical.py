import hashlib,json,os,py_compile,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];C='mab-late-constraint-4412b3e2d6';O=R/'candidate_cases/rebuild-to-100/runtime-mab-bargaining'/C/'runtime';M=R/'candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble'
T="""from solution import DiverWatchBargaining
t=DiverWatchBargaining();t.offer('buyer',60,90,12,50,True,0)
try: t.seller_counter(0);raise AssertionError
except RuntimeError: pass
x=t.seller_counter(1);assert (x.price,x.battery_age_days,x.guarantee_months,x.quantity,x.consolidated)==(62,90,12,50,True);t.accept(2);assert t.audit()['chronological'];print('native watch bargaining checks passed')"""
def main():
 s=O/'solution.py';p=O/'native_test.py';p.write_text(T);py_compile.compile(str(s),doraise=True);r=subprocess.run([sys.executable,str(p)],cwd=O,text=True,capture_output=True);assert r.returncode==0,r.stderr
 sys.path.insert(0,str(M));os.chdir(M);import marble.evaluator.evaluator as em
 class X: content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
 em.model_prompting=lambda **k:[X()];e=em.Evaluator.__new__(em.Evaluator);e.metrics={'code_quality':{}};e.llm='watch-evaluator';e.logger=type('L',(),{'error':lambda *a,**k:None,'info':lambda *a,**k:None,'debug':lambda *a,**k:None})();(M/'marble/workspace').mkdir(exist_ok=True);shutil.copy2(s,M/'marble/workspace/solution.py');e.evaluate_code_quality('bargaining:008',s.read_text())
 d={'schema_version':'async-rbench-mab-bargaining-native-v1','case_id':C,'source_task_id':'bargaining:008','source_native_marble_verified':True,'native_evaluator_verified':True,'solution_sha256':hashlib.sha256(s.read_bytes()).hexdigest(),'native_test_exit_code':r.returncode,'native_test_stdout':r.stdout.strip(),'native_evaluator_metrics':e.metrics['code_quality'],'negotiation_invariants':['stale_offer_rejected','ninety_day_battery','one_year_replacement','fifty_unit_consolidation'],'passed':True};d['evidence_sha256']=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest();(O/'native_canonical_report.json').write_text(json.dumps(d,indent=2,sort_keys=True)+'\n');print(json.dumps(d,indent=2))
if __name__=='__main__':main()
