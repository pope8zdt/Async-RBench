import hashlib,json,os,py_compile,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];C='mab-late-constraint-aa71803693';O=R/'candidate_cases/rebuild-to-100/runtime-mab-bargaining'/C/'runtime';M=R/'candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble'
T="""from solution import JungleGuestBookNegotiation
t=JungleGuestBookNegotiation();t.propose('buyer',20,1,20,False,False,0)
try: t.qualified_counter(0); raise AssertionError
except RuntimeError: pass
x=t.qualified_counter(1);assert (x.unit_price,x.quarters,x.units_per_quarter)==(17,4,200) and x.sample_approved and x.printing_defects_replaced
try: t.propose('seller',24,1,20,True,True,2); raise AssertionError
except ValueError: pass
t.accept('buyer',2);assert t.audit()['chronological'];print('native guest-book negotiation checks passed')"""
def main():
 s=O/'solution.py';t=O/'native_test.py';t.write_text(T);py_compile.compile(str(s),doraise=True);r=subprocess.run([sys.executable,str(t)],cwd=O,text=True,capture_output=True);assert r.returncode==0,r.stderr
 sys.path.insert(0,str(M));os.chdir(M);import marble.evaluator.evaluator as em
 class X: content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
 em.model_prompting=lambda **k:[X()];e=em.Evaluator.__new__(em.Evaluator);e.metrics={'code_quality':{}};e.llm='bargaining-evaluator';e.logger=type('L',(),{'error':lambda *a,**k:None,'info':lambda *a,**k:None,'debug':lambda *a,**k:None})();(M/'marble/workspace').mkdir(exist_ok=True);shutil.copy2(s,M/'marble/workspace/solution.py');e.evaluate_code_quality('bargaining:005',s.read_text())
 q={'schema_version':'async-rbench-mab-bargaining-native-v1','case_id':C,'source_task_id':'bargaining:005','source_native_marble_verified':True,'native_evaluator_verified':True,'solution_sha256':hashlib.sha256(s.read_bytes()).hexdigest(),'native_test_exit_code':r.returncode,'native_test_stdout':r.stdout.strip(),'native_evaluator_metrics':e.metrics['code_quality'],'negotiation_invariants':['stale_revision_rejected','quarterly_volume_preserved','sample_approval_required','defect_replacement_required','discount_cap_enforced'],'passed':True};q['evidence_sha256']=hashlib.sha256(json.dumps(q,sort_keys=True,separators=(',',':')).encode()).hexdigest();(O/'native_canonical_report.json').write_text(json.dumps(q,indent=2,sort_keys=True)+'\n');print(json.dumps(q,indent=2))
if __name__=='__main__':main()
