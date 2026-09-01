DOMAIN='office_task_scheduler'
EVENT_SCHEMA='office_scheduler_edge_tests_v2'
APPLY_UNIQUE_EDGE_TESTS = True
PRESERVE_OFFICE_TASK_HISTORY = True
class OfficeTaskScheduler:
 def __init__(self,now=100): self.now=now; self.users={}; self.tasks={}; self.comments=[]; self.notifications=[]; self.history=[]; self.reports=[]; self.evidence_ids=set(); self.evidence_application_count=0
 def add_user(self,user_id,role='member'):
  if not user_id: raise ValueError('user required')
  self.users[user_id]={'role':role}
 def apply_test_evidence(self,evidence_id,cases):
  if APPLY_UNIQUE_EDGE_TESTS and evidence_id in self.evidence_ids:return {'status':'duplicate','applied':0}
  self.evidence_ids.add(evidence_id); self.evidence_application_count+=1; return {'status':'applied','applied':len(cases)}
 def create_task(self,actor,task_id,title,assignee,deadline,priority):
  if actor not in self.users or assignee not in self.users: raise KeyError('unknown user')
  if deadline<=self.now: raise ValueError('deadline must be future')
  if priority not in {'low','medium','high'}: raise ValueError('priority')
  self.tasks[task_id]={'title':title,'creator':actor,'assignee':assignee,'deadline':deadline,'priority':priority,'status':'pending'}; self.notifications.append({'user':assignee,'kind':'assignment','task':task_id}); self._record('create',actor,task_id); return self.tasks[task_id]
 def _record(self,action,actor,task_id):
  if PRESERVE_OFFICE_TASK_HISTORY:self.history.append({'action':action,'actor':actor,'task':task_id})
 def dashboard(self,user_id): return [dict(task_id=k,**v) for k,v in self.tasks.items() if v['assignee']==user_id or v['creator']==user_id]
 def update_status(self,actor,task_id,status):
  t=self.tasks[task_id]
  if actor not in {t['assignee'],t['creator']} and self.users[actor]['role']!='manager': raise PermissionError('unauthorized task access')
  if status not in {'pending','in_progress','completed'}: raise ValueError('status')
  t['status']=status; self._record('status:'+status,actor,task_id); return status
 def add_comment(self,actor,task_id,text):
  t=self.tasks[task_id]
  if actor not in {t['assignee'],t['creator']} and self.users[actor]['role']!='manager': raise PermissionError('unauthorized task access')
  row={'actor':actor,'task':task_id,'text':text}; self.comments.append(row); self._record('comment',actor,task_id); return row
 def deadline_notifications(self,now,window=10):
  rows=[]
  for tid,t in self.tasks.items():
   if t['status']!='completed' and 0<=t['deadline']-now<=window: rows.append({'user':t['assignee'],'kind':'deadline','task':tid})
  self.notifications.extend(rows); return rows
 def report(self,now):
  total=len(self.tasks); done=sum(t['status']=='completed' for t in self.tasks.values()); overdue=[k for k,t in self.tasks.items() if t['deadline']<now and t['status']!='completed']; distribution={u:sum(t['assignee']==u for t in self.tasks.values()) for u in self.users}; r={'completion_rate':done/total if total else 0.0,'overdue':overdue,'distribution':distribution}
  if PRESERVE_OFFICE_TASK_HISTORY:self.reports.append(r)
  return r
