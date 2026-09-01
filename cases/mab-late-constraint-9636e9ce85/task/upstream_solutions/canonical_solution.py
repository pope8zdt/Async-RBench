DOMAIN='office_task_collaboration_manager'
EVENT_SCHEMA='office_dependency_sla_policy_v2'
ENFORCE_DEPENDENCY_POLICY = True
PRESERVE_TASK_AUDIT = True
class OfficeTaskCollaborationManager:
 def __init__(self):
  self.users={}; self.tasks={}; self.comments=[]; self.audit=[]; self.alerts=[]; self.reports=[]; self.policy=None
 def add_user(self,user_id,role,department):
  if role not in {'employee','manager','admin'}: raise ValueError('invalid role')
  self.users[user_id]={'role':role,'department':department}
 def apply_policy(self,policy):
  required={'completion_requires','overdue_alert_roles','allowed_statuses'}
  if not required<=set(policy): raise ValueError('incomplete policy')
  self.policy=dict(policy); return self.policy
 def create_task(self,actor,task_id,title,assignee,department,priority='normal',due_at=None,dependencies=()):
  if actor not in self.users or assignee not in self.users or task_id in self.tasks: raise ValueError('invalid task')
  self.tasks[task_id]={'title':title,'assignee':assignee,'department':department,'priority':priority,'due_at':due_at,'dependencies':list(dependencies),'status':'todo','approved_by':None}; self._audit('create',actor,task_id); return self.tasks[task_id]
 def _audit(self,action,actor,task_id):
  if PRESERVE_TASK_AUDIT:self.audit.append({'action':action,'actor':actor,'task_id':task_id})
 def delegate(self,actor,task_id,new_assignee):
  if self.users[actor]['role'] not in {'manager','admin'}: raise PermissionError('manager required')
  self.tasks[task_id]['assignee']=new_assignee; self._audit('delegate',actor,task_id)
 def comment(self,actor,task_id,text):
  row={'actor':actor,'task_id':task_id,'text':text}
  if PRESERVE_TASK_AUDIT:self.comments.append(row); self._audit('comment',actor,task_id)
  return row
 def approve(self,manager,task_id):
  if self.users[manager]['role'] not in {'manager','admin'}: raise PermissionError('manager required')
  self.tasks[task_id]['approved_by']=manager; self._audit('approve',manager,task_id)
 def update_status(self,actor,task_id,status):
  t=self.tasks[task_id]
  if ENFORCE_DEPENDENCY_POLICY:
   if not self.policy: raise RuntimeError('policy unresolved')
   if status not in self.policy['allowed_statuses']: raise ValueError('invalid status')
   if status=='done' and any(self.tasks[d]['status']!='done' for d in t['dependencies']): raise RuntimeError('dependencies incomplete')
   if status=='done' and t['priority']=='high' and not t['approved_by']: raise PermissionError('high priority approval required')
  t['status']=status; self._audit('status:'+status,actor,task_id); return status
 def generate_overdue_alerts(self,now):
  if ENFORCE_DEPENDENCY_POLICY and not self.policy: raise RuntimeError('policy unresolved')
  for tid,t in self.tasks.items():
   if t['due_at'] is not None and t['due_at']<now and t['status']!='done':
    recipients=[t['assignee']]+[u for u,v in self.users.items() if v['role']=='manager' and v['department']==t['department']]
    self.alerts.append({'task_id':tid,'recipients':sorted(set(recipients))})
  return list(self.alerts)
 def report(self,department):
  rows=[t for t in self.tasks.values() if t['department']==department]; report={'department':department,'total':len(rows),'done':sum(t['status']=='done' for t in rows),'blocked':sum(t['status']=='blocked' for t in rows)}
  if PRESERVE_TASK_AUDIT:self.reports.append(report)
  return report
