DOMAIN='team_collaboration_manager'
EVENT_SCHEMA='team_performance_metric_contract_v2'
USE_RETURNED_METRIC_CONTRACT = True
PRESERVE_COLLABORATION_HISTORY = True
class TeamCollaborationManager:
 def __init__(self): self.users={}; self.projects={}; self.tasks={}; self.messages=[]; self.feedback=[]; self.contract=None
 def add_user(self,user_id):
  if not user_id or user_id in self.users: raise ValueError('unique user required')
  self.users[user_id]={'projects':set()}; return self.users[user_id]
 def apply_metric_contract(self,contract):
  if contract.get('duration_origin')!='task_created_at' or contract.get('assignment_policy')!='unique_member_per_task': raise ValueError('invalid metric contract')
  self.contract=dict(contract); return self.contract
 def create_project(self,project_id,name,start_date,end_date,description,members):
  if not name or start_date>end_date or not set(members)<=set(self.users): raise ValueError('invalid project')
  self.projects[project_id]={'name':name,'start':start_date,'end':end_date,'description':description,'members':set(members)}
  for member in members:self.users[member]['projects'].add(project_id)
  return self.projects[project_id]
 def create_task(self,task_id,project_id,assignee,deadline,created_at):
  project=self.projects[project_id]
  if assignee not in project['members'] or not project['start']<=deadline<=project['end']: raise ValueError('invalid assignment or deadline')
  if task_id in self.tasks: raise ValueError('concurrent duplicate task')
  self.tasks[task_id]={'project':project_id,'assignee':assignee,'deadline':deadline,'created_at':float(created_at),'completed_at':None,'status':'not started'}; return self.tasks[task_id]
 def set_status(self,task_id,status,at=None):
  allowed={'not started':['in progress'],'in progress':['completed'],'completed':[]}; task=self.tasks[task_id]
  if status not in allowed[task['status']]: raise ValueError('invalid status transition')
  task['status']=status
  if status=='completed': task['completed_at']=float(at)
  return task
 def post_message(self,user_id,text,project_id=None,task_id=None,attachment=None):
  if user_id not in self.users or not text or (project_id is None and task_id is None): raise ValueError('invalid message')
  row={'user':user_id,'text':text,'project':project_id,'task':task_id,'attachment':attachment}
  if PRESERVE_COLLABORATION_HISTORY:self.messages.append(row)
  return row
 def add_feedback(self,reviewer,member,rating,note):
  if reviewer not in self.users or member not in self.users or not 1<=rating<=5: raise ValueError('invalid feedback')
  row={'reviewer':reviewer,'member':member,'rating':rating,'note':note}
  if PRESERVE_COLLABORATION_HISTORY:self.feedback.append(row)
  return row
 def dashboard(self,user_id):
  if USE_RETURNED_METRIC_CONTRACT and not self.contract: raise RuntimeError('metric authority required')
  assigned=[t for t in self.tasks.values() if t['assignee']==user_id]; completed=[t for t in assigned if t['status']=='completed']
  durations=[t['completed_at']-t['created_at'] for t in completed]
  ratings=[f['rating'] for f in self.feedback if f['member']==user_id]
  return {'assigned':len(assigned),'completion_rate':(len(completed)/len(assigned) if assigned else 0.0),'average_completion_time':(sum(durations)/len(durations) if durations else None),'average_rating':(sum(ratings)/len(ratings) if ratings else None)}
 def export_project_csv(self,project_id):
  rows=['task_id,assignee,status,deadline']
  rows += [f"{tid},{t['assignee']},{t['status']},{t['deadline']}" for tid,t in sorted(self.tasks.items()) if t['project']==project_id]
  return '\n'.join(rows)+'\n'
