from __future__ import annotations
import hashlib
DOMAIN='financial_collaborator'; EVENT_SCHEMA='ledger_invariants_v2'
class FinancialCollaborator:
 def __init__(self): self.users={};self.sessions={};self.groups={};self.ledger=[];self.notifications=[];self.messages=[];self.operations=set()
 def register(self,user,password):
  if not user or len(password)<6: raise ValueError('credentials')
  if user in self.users: raise ValueError('duplicate')
  self.users[user]=hashlib.sha256(password.encode()).hexdigest()
 def login(self,user,password):
  if self.users.get(user)!=hashlib.sha256(password.encode()).hexdigest(): raise PermissionError('login')
  token=hashlib.sha256((user+password).encode()).hexdigest();self.sessions[token]=user;return token
 def user(self,token):
  if token not in self.sessions: raise PermissionError('session')
  return self.sessions[token]
 def create_group(self,token,gid): self.groups[gid]={'owner':self.user(token),'members':{self.user(token)},'goal':None,'deadline':None,'milestones':[]};return gid
 def join_group(self,token,gid): self.groups[gid]['members'].add(self.user(token))
 def set_goal(self,token,gid,amount,deadline,milestones=()):
  u=self.user(token);g=self.groups[gid]
  if u!=g['owner'] or amount<=0 or any(x<=0 or x>amount for x in milestones): raise ValueError('goal')
  g.update(goal=float(amount),deadline=deadline,milestones=sorted(set(map(float,milestones))))
 def contribute(self,token,gid,amount,operation_id):
  u=self.user(token);g=self.groups[gid]
  if u not in g['members'] or amount<=0: raise ValueError('contribution')
  if operation_id in self.operations: return False
  self.operations.add(operation_id);self.ledger.append({'group':gid,'user':u,'amount':float(amount),'operation_id':operation_id});return True
 def refund(self,token,gid,amount,operation_id):
  u=self.user(token)
  if amount<=0: raise ValueError('refund')
  if operation_id in self.operations:return False
  if sum(x['amount'] for x in self.ledger if x['group']==gid and x['user']==u)<amount: raise ValueError('over-refund')
  self.operations.add(operation_id);self.ledger.append({'group':gid,'user':u,'amount':-float(amount),'operation_id':operation_id});return True
 def dashboard(self,token,gid):
  u=self.user(token);g=self.groups[gid]
  if u not in g['members']:raise PermissionError('group')
  by={m:sum(x['amount'] for x in self.ledger if x['group']==gid and x['user']==m) for m in g['members']}; total=round(sum(by.values()),2); goal=g['goal']
  return {'total':total,'by_user':by,'remaining':max(0,round(goal-total,2)),'milestones_reached':[m for m in g['milestones'] if total>=m]}
 def chat(self,token,gid,text):
  u=self.user(token)
  if u not in self.groups[gid]['members'] or not text:raise PermissionError('chat')
  self.messages.append((gid,u,text))
 def remind(self,gid,kind): self.notifications.extend((u,kind,gid) for u in sorted(self.groups[gid]['members']))

# independently frozen equivalent implementation
