from __future__ import annotations
DOMAIN='photo_collab_editor'; EVENT_SCHEMA='socket_revision_contract_v2'
class PhotoCollabEditor:
 def __init__(self):self.users=set();self.sessions={};self.operations=set();self.events=[];self.chat_log=[]
 def register(self,user):
  if not user or user in self.users:raise ValueError('user')
  self.users.add(user)
 def create_session(self,user,sid,photo):
  if user not in self.users:raise PermissionError('user')
  self.sessions[sid]={'owner':user,'members':{user},'photo':photo,'revision':0,'actions':[],'presence':{user}}
 def join(self,user,sid):
  if user not in self.users:raise PermissionError('user')
  self.sessions[sid]['members'].add(user);self.sessions[sid]['presence'].add(user)
 def apply(self,user,sid,operation_id,base_revision,tool,payload):
  s=self.sessions[sid]
  if user not in s['members']:raise PermissionError('session')
  if operation_id in self.operations:return {'status':'duplicate','revision':s['revision']}
  if base_revision!=s['revision']:return {'status':'conflict','revision':s['revision']}
  if tool not in {'filter','color','background_remove'}:raise ValueError('tool')
  self.operations.add(operation_id);s['revision']+=1;a={'operation_id':operation_id,'base_revision':base_revision,'revision':s['revision'],'user':user,'tool':tool,'payload':payload};s['actions'].append(a);self.events.append({'room':sid,'ack':operation_id,'broadcast':a});return {'status':'applied','revision':s['revision']}
 def leave(self,user,sid):self.sessions[sid]['presence'].discard(user)
 def chat(self,user,sid,text):
  if user not in self.sessions[sid]['members'] or not text:raise PermissionError('chat')
  self.chat_log.append((sid,user,text))
 def history(self,user,sid):
  if user not in self.sessions[sid]['members']:raise PermissionError('session')
  return list(self.sessions[sid]['actions'])
