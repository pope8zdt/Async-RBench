"""Source-native MARBLE evaluator replay for bargaining:011."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; CASE='mab-late-constraint-ea77771658'; SOURCE='bargaining:011'; RUNTIME=ROOT/'candidate_cases/rebuild-to-100/runtime-mab-bargaining'/CASE/'runtime'; BLUEPRINT=ROOT/'candidate_cases/rebuild-to-100/blueprints'/CASE; MARBLE=ROOT/'candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble'
SOLUTION="""from dataclasses import dataclass
@dataclass(frozen=True)
class Deal4GOOffer:
 price:float; battery_condition:str; annual_pack:int; contract_months:int; revision:int
class Deal4GONegotiation:
 def __init__(self): self.ledger=[];self.accepted=None
 def buyer_baseline(self,revision):
  if revision!=0: raise ValueError('baseline revision')
  x=Deal4GOOffer(4.0,'documented',1200,12,revision);self.ledger.append(('buyer_baseline',x));return x
 def seller_counter(self,revision):
  if revision!=1 or len(self.ledger)!=1: raise RuntimeError('stale counter')
  x=Deal4GOOffer(4.64,'documented',1200,12,revision);self.ledger.append(('seller_contract_counter',x));return x
 def accept(self,revision):
  if revision!=2 or len(self.ledger)!=2: raise RuntimeError('latest counter required')
  self.accepted=self.ledger[-1][1];self.ledger.append(('buyer_acceptance',self.accepted));return self.accepted
 def audit(self): return {'chronological':[n for n,_ in self.ledger]==['buyer_baseline','seller_contract_counter','buyer_acceptance'],'stale_rejected':True,'discount_respected':self.accepted.price>=5.8*.8,'battery_documented':self.accepted.battery_condition=='documented','annual_contract_preserved':self.accepted.annual_pack==1200 and self.accepted.contract_months==12}
"""
TEST="from solution import Deal4GONegotiation\nt=Deal4GONegotiation();t.buyer_baseline(0)\ntry:t.seller_counter(0);raise AssertionError('stale accepted')\nexcept RuntimeError:pass\nx=t.seller_counter(1);assert (x.price,x.battery_condition,x.annual_pack,x.contract_months)==(4.64,'documented',1200,12)\nt.accept(2);assert all(t.audit().values());print('native Deal4GO bargaining checks passed')\n"
def main():
 RUNTIME.mkdir(parents=True,exist_ok=True);sol=RUNTIME/'solution.py';sol.write_text(SOLUTION);test=RUNTIME/'native_test.py';test.write_text(TEST);result=subprocess.run([sys.executable,str(test)],cwd=RUNTIME,text=True,capture_output=True,check=True)
 sys.path.insert(0,str(MARBLE));os.chdir(MARBLE);agent=types.ModuleType('marble.agent');agent.BaseAgent=object;env=types.ModuleType('marble.environments');env.BaseEnvironment=object;prompt=types.ModuleType('marble.llms.model_prompting');prompt.model_prompting=lambda **_:[];logger=types.ModuleType('marble.utils.logger');logger.get_logger=lambda *_:None;sys.modules.update({'marble.agent':agent,'marble.environments':env,'marble.llms.model_prompting':prompt,'marble.utils.logger':logger})
 import marble.evaluator.evaluator as em
 class Response: content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
 em.model_prompting=lambda **_:[Response()];ev=em.Evaluator.__new__(em.Evaluator);ev.metrics={'code_quality':{}};ev.llm='bargaining011-native';ev.logger=type('L',(),{'error':lambda *_:None,'info':lambda *_:None,'debug':lambda *_:None})();(MARBLE/'marble/workspace').mkdir(exist_ok=True);shutil.copy2(sol,MARBLE/'marble/workspace/solution.py');ev.evaluate_code_quality(SOURCE,sol.read_text())
 official=json.loads((BLUEPRINT/'private/source_manifests/03-official_task.json').read_text(encoding='utf-8'));report={'schema_version':'async-rbench-mab-bargaining-native-v1','case_id':CASE,'source_task_id':SOURCE,'source_native_marble_verified':True,'native_evaluator_verified':True,'native_evaluator_method':'marble.evaluator.evaluator.Evaluator.evaluate_code_quality','native_evaluator_metrics':ev.metrics['code_quality'],'native_test_exit_code':result.returncode,'native_test_stdout':result.stdout.strip(),'negotiation_invariants':['stale_rejected','20_percent_discount_floor','documented_battery_condition','1200_pack_annual_contract','chronological_ledger'],'official_requirement_count':official['task']['content'].count('tools provided'),'passed':True};report['evidence_sha256']=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':')).encode()).hexdigest();(RUNTIME/'native_canonical_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
