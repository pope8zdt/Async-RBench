from dataclasses import dataclass,field
from threading import RLock
import hashlib
@dataclass
class Review:
 id:int; repo:str; branch:str; owner:str; code:str; version:int=0; status:str='open'; reviewers:set=field(default_factory=set); annotations:list=field(default_factory=list); chat:list=field(default_factory=list); history:list=field(default_factory=list)
class CodeSquad:
 def __init__(self): self.lock=RLock(); self.users={}; self.tokens={}; self.reviews={}; self.next=1; self.events=[]
 def register(self,u,p,role='developer'):
  if len(p)<8 or role not in {'developer','senior','admin'}: raise ValueError('invalid')
  self.users[u]=(hashlib.sha256(p.encode()).hexdigest(),role)
 def login(self,u,p):
  if u not in self.users or self.users[u][0]!=hashlib.sha256(p.encode()).hexdigest(): raise PermissionError('bad credentials')
  t=hashlib.sha256(f'{u}:{len(self.tokens)}'.encode()).hexdigest(); self.tokens[t]=u; return t
 def actor(self,t):
  if t not in self.tokens: raise PermissionError('auth required')
  return self.tokens[t]
 def create_review(self,t,repo,branch,code):
  u=self.actor(t); r=Review(self.next,repo,branch,u,code,reviewers={u}); self.reviews[r.id]=r; self.next+=1; return r
 def add_reviewer(self,t,rid,u):
  a=self.actor(t); r=self.reviews[rid]
  if a!=r.owner or u not in self.users: raise PermissionError('owner required')
  r.reviewers.add(u)
 def push(self,t,rid,code,expected_version):
  with self.lock:
   u=self.actor(t); r=self.reviews[rid]
   if u not in r.reviewers or expected_version!=r.version: raise RuntimeError('version conflict')
   r.history.append({'version':r.version,'code':r.code}); r.code=code; r.version+=1; self.events.append({'review':rid,'version':r.version,'kind':'git_push'}); return r
 def annotate(self,t,rid,line,text):
  u=self.actor(t); r=self.reviews[rid]
  if u not in r.reviewers: raise PermissionError('reviewer required')
  r.annotations.append({'author':u,'line':line,'text':text,'version':r.version})
 def send_chat(self,t,rid,text,kind='message'):
  u=self.actor(t); r=self.reviews[rid]
  if u not in r.reviewers or kind not in {'message','code','error_log'}: raise PermissionError('reviewer required')
  r.chat.append({'author':u,'kind':kind,'text':text})
 def transition(self,t,rid,status):
  u=self.actor(t); r=self.reviews[rid]
  allowed={'open':{'resolved','escalated'},'resolved':{'reopened'},'reopened':{'resolved','escalated'},'escalated':{'resolved'}}
  if u not in r.reviewers or status not in allowed.get(r.status,set()): raise ValueError('invalid transition')
  r.status=status
 def dashboard(self,t,status=None,query=''):
  u=self.actor(t); rows=[r for r in self.reviews.values() if u in r.reviewers and (status is None or r.status==status) and query.lower() in (r.repo+' '+r.branch+' '+r.code).lower()]; return [{'id':r.id,'status':r.status,'version':r.version} for r in rows]
