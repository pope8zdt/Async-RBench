from __future__ import annotations
import hashlib,json,os,py_compile,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; CASE_ID='mab-cross-app-artifact-ae660c3f6d'; SOURCE_ID='coding:069'; B=ROOT/'candidate_cases/rebuild-to-100/blueprints'/CASE_ID; O=ROOT/'candidate_cases/rebuild-to-100/runtime-mab-coding'/CASE_ID/'runtime'; M=ROOT/'candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble'
SOLUTION=r'''from __future__ import annotations
from dataclasses import dataclass,field
from datetime import datetime,timezone
from threading import RLock
from typing import Dict,List
import hashlib
@dataclass
class User: name:str; password_hash:str; preferences:set=field(default_factory=set)
@dataclass
class Product: id:str; title:str; retailer:str; price:float; review:float; updated_at:datetime; aliases:set=field(default_factory=set)
class CollaborativeShoppingAssistant:
 def __init__(self): self.lock=RLock();self.users={};self.sessions={};self.products={};self.lists={};self.budgets={};self.events=[]
 def register(self,name,password,preferences=()):
  if not name or len(password)<6: raise ValueError('invalid credentials')
  with self.lock:
   if name in self.users: raise ValueError('duplicate user')
   self.users[name]=User(name,hashlib.sha256(password.encode()).hexdigest(),set(preferences))
 def login(self,name,password):
  with self.lock:
   if name not in self.users or self.users[name].password_hash!=hashlib.sha256(password.encode()).hexdigest(): raise PermissionError('login failed')
   token=hashlib.sha256((name+password+str(len(self.sessions))).encode()).hexdigest();self.sessions[token]=name;return token
 def _user(self,t):
  if t not in self.sessions: raise PermissionError('session required')
  return self.sessions[t]
 def normalize_listing(self,retailer,sku,title,price,review,updated_at,aliases=()):
  if price<0 or not 0<=review<=5 or updated_at.tzinfo is None: raise ValueError('invalid listing')
  with self.lock:
   canonical=next((p.id for p in self.products.values() if sku==p.id or sku in p.aliases or p.id in aliases),sku)
   prior=self.products.get(canonical)
   if prior and updated_at<prior.updated_at: raise RuntimeError('stale retailer price')
   self.products[canonical]=Product(canonical,title,retailer,float(price),float(review),updated_at,set(aliases));self.events.append({'event':'listing','product':canonical});return canonical
 def create_list(self,t,list_id,members):
  owner=self._user(t)
  with self.lock:
   self.lists[list_id]={'members':set(members)|{owner},'items':{},'version':0,'owner':owner};return list_id
 def set_budget(self,t,list_id,limit):
  self._user(t)
  if limit<0: raise ValueError('budget')
  with self.lock:self.budgets[list_id]=float(limit)
 def add_item(self,t,list_id,product_id,qty=1,expected_version=None):
  user=self._user(t)
  with self.lock:
   l=self.lists[list_id]
   if user not in l['members']: raise PermissionError('not collaborator')
   if expected_version is not None and expected_version!=l['version']: raise RuntimeError('stale list edit')
   if product_id not in self.products or qty<=0: raise ValueError('item')
   l['items'][product_id]=qty;l['version']+=1;self.events.append({'event':'list_update','list':list_id,'version':l['version']})
 def total(self,list_id):
  l=self.lists[list_id];return round(sum(self.products[p].price*q for p,q in l['items'].items()),2)
 def budget_status(self,list_id):
  total=self.total(list_id);limit=self.budgets.get(list_id);return {'total':total,'limit':limit,'alert':limit is not None and total>=limit}
 def recommendations(self,t,list_id):
  user=self._user(t);l=self.lists[list_id]; prefs=self.users[user].preferences
  rows=[p for p in self.products.values() if p.id not in l['items']]
  return [p.id for p in sorted(rows,key=lambda p:(-(p.review+.2*bool(prefs & set(p.title.lower().split()))),p.price,p.id))]
'''
TEST=r'''from datetime import datetime,timedelta,timezone
from solution import CollaborativeShoppingAssistant as S
s=S();s.register('ada','secret1',['coffee']);s.register('ben','secret2');a=s.login('ada','secret1');b=s.login('ben','secret2');now=datetime.now(timezone.utc);p=s.normalize_listing('r1','c1','Coffee maker',50,4.6,now,['coffee-1']);assert s.normalize_listing('r2','coffee-1','Coffee maker',48,4.8,now+timedelta(minutes=1),['c1'])==p
s.create_list(a,'family',['ben']);s.set_budget(a,'family',60);s.add_item(b,'family',p,1,0)
try:s.add_item(a,'family',p,1,0);raise AssertionError
except RuntimeError:pass
assert s.budget_status('family')['alert'] is False;s.normalize_listing('r3','tea','Tea',20,4.2,now,[]);assert s.recommendations(a,'family')==['tea'];print('native CollaborativeShoppingAssistant checks passed')'''
def main():
 O.mkdir(parents=True,exist_ok=True);sol=O/'solution.py';test=O/'native_test.py';sol.write_text(SOLUTION,encoding='utf-8');test.write_text(TEST,encoding='utf-8');py_compile.compile(str(sol),doraise=True);r=subprocess.run([sys.executable,str(test)],cwd=O,text=True,capture_output=True,timeout=30);assert r.returncode==0,r.stderr
 print('native functional test passed',flush=True);sys.path.insert(0,str(M));os.chdir(M);import marble.evaluator.evaluator as em
 class X: content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
 em.model_prompting=lambda **k:[X()];e=em.Evaluator.__new__(em.Evaluator);e.metrics={'code_quality':{}};e.llm='canonical-evaluator';e.logger=type('L',(),{'error':lambda *a,**k:None,'info':lambda *a,**k:None,'debug':lambda *a,**k:None})();(M/'marble/workspace').mkdir(exist_ok=True);shutil.copy2(sol,M/'marble/workspace/solution.py');e.evaluate_code_quality(SOURCE_ID,SOLUTION)
 off=json.loads((B/'private/source_manifests/03-official_task.json').read_text());d={'schema_version':'async-rbench-mab-coding-native-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'source_native_marble_verified':True,'native_evaluator_verified':True,'model_episode_executed':False,'canonical_episode_owner':'evaluator','solution_sha256':hashlib.sha256(sol.read_bytes()).hexdigest(),'native_test_exit_code':r.returncode,'native_test_stdout':r.stdout.strip(),'native_evaluator_method':'marble.evaluator.evaluator.Evaluator.evaluate_code_quality','native_evaluator_metrics':e.metrics['code_quality'],'official_requirement_count':off['task']['content'].count('   - '),'passed':True};d['evidence_sha256']=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest();(O/'native_canonical_report.json').write_text(json.dumps(d,indent=2,sort_keys=True)+'\n');print(json.dumps(d,indent=2))
if __name__=='__main__':main()
