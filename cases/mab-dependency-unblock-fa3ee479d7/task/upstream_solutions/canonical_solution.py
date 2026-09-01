DOMAIN='collaborate_craft'
EVENT_SCHEMA='craft_group_integrity_v2'
ENFORCE_GROUP_INTEGRITY = True
PRESERVE_CRAFT_COMMUNITY = True
class CollaborateCraft:
 def __init__(self): self.profiles={}; self.posts={}; self.groups={}; self.comments={}; self.messages=[]; self.contract=None
 def apply_integrity_contract(self,contract):
  if set(contract.get('leader_only',[]))!={'invite','assign_task'}: raise ValueError('invalid integrity contract')
  self.contract=dict(contract); return self.contract
 def create_profile(self,user,bio,picture):
  if not all([user,bio,picture]): raise ValueError('profile fields required')
  self.profiles[user]={'bio':bio,'picture':picture}; return self.profiles[user]
 def post_project(self,post_id,user,media_type,media,description,tags):
  if ENFORCE_GROUP_INTEGRITY and (not self.contract or media_type not in self.contract['media_types']): raise ValueError('invalid media')
  if user not in self.profiles or not description or not tags: raise ValueError('invalid post')
  self.posts[post_id]={'user':user,'media_type':media_type,'media':media,'description':description,'tags':set(tags)}; return self.posts[post_id]
 def create_group(self,group_id,leader,title):
  if leader not in self.profiles: raise KeyError(leader)
  self.groups[group_id]={'leader':leader,'title':title,'members':{leader},'tasks':{},'progress':0}; return self.groups[group_id]
 def invite(self,actor,group_id,user):
  g=self.groups[group_id]
  if ENFORCE_GROUP_INTEGRITY and actor!=g['leader']: raise PermissionError('leader required')
  if user not in self.profiles: raise KeyError(user)
  g['members'].add(user)
 def assign_task(self,actor,group_id,task_id,assignee):
  g=self.groups[group_id]
  if ENFORCE_GROUP_INTEGRITY and (actor!=g['leader'] or assignee not in g['members']): raise PermissionError('leader/member required')
  g['tasks'][task_id]={'assignee':assignee,'done':False}
 def complete_task(self,user,group_id,task_id):
  t=self.groups[group_id]['tasks'][task_id]
  if t['assignee']!=user: raise PermissionError('wrong assignee')
  t['done']=True; g=self.groups[group_id]; g['progress']=round(sum(x['done'] for x in g['tasks'].values())/len(g['tasks']),3); return g['progress']
 def comment(self,user,target,text):
  if user not in self.profiles or not text: raise ValueError('invalid comment')
  cid=f'c{len(self.comments)+1}'; self.comments[cid]={'user':user,'target':target,'text':text,'score':0}; return cid
 def vote(self,user,comment_id,value):
  if ENFORCE_GROUP_INTEGRITY and value not in self.contract['comment_votes']: raise ValueError('vote must be -1 or 1')
  self.comments[comment_id]['score']+=value; return self.comments[comment_id]['score']
 def message(self,sender,recipient,text,group=False):
  if group and sender not in self.groups[recipient]['members']: raise PermissionError('not group member')
  if not group and recipient not in self.profiles: raise KeyError(recipient)
  row={'sender':sender,'recipient':recipient,'text':text,'group':group}; self.messages.append(row); return row
 def search(self,query):
  q=query.lower(); users=[u for u,p in self.profiles.items() if q in u.lower() or q in p['bio'].lower()]; posts=[k for k,p in self.posts.items() if q in p['description'].lower() or any(q in t.lower() for t in p['tags'])]; groups=[k for k,g in self.groups.items() if q in g['title'].lower()]; return {'users':sorted(users),'posts':sorted(posts),'groups':sorted(groups)}
