DOMAIN='team_sync_pro'
EVENT_SCHEMA='department_rbac_api_v3'
ENFORCE_RBAC = True
PRESERVE_AUDIT = True
ENDPOINTS={
 ('POST','/tasks'):{'roles':{'manager','admin'},'fields':{'task_id','title','department'}},
 ('POST','/resources/allocate'):{'roles':{'manager','admin'},'fields':{'task_id','resource_id','department'}},
 ('POST','/messages'):{'roles':{'member','manager','admin'},'fields':{'channel','message','department'}},
 ('GET','/performance'):{'roles':{'manager','admin'},'fields':{'department'}},
}


class TeamSyncPro:
 def __init__(self): self.users={}; self.tasks={}; self.allocations=[]; self.messages=[]; self.reports=[]; self.audit=[]
 def add_user(self,user_id,department,role):
  if role not in {'member','manager','admin'}: raise ValueError('invalid role')
  self.users[user_id]={'department':department,'role':role}
 def authorize(self,actor,method,path,fields,target_department):
  if not ENFORCE_RBAC: return True
  user=self.users.get(actor); spec=ENDPOINTS.get((method,path))
  if not user or not spec or set(fields)!=spec['fields']: raise PermissionError('endpoint contract rejected')
  if user['role'] not in spec['roles']: raise PermissionError('role rejected')
  if user['role']!='admin' and user['department']!=target_department: raise PermissionError('cross department rejected')
  return True
 def create_task(self,actor,task_id,title,department):
  self.authorize(actor,'POST','/tasks',{'task_id','title','department'},department); self.tasks[task_id]={'title':title,'department':department,'status':'open'}
  if PRESERVE_AUDIT:self.audit.append(('task_created',actor,task_id)); return self.tasks[task_id]
 def allocate(self,actor,task_id,resource_id,department):
  self.authorize(actor,'POST','/resources/allocate',{'task_id','resource_id','department'},department); row=(task_id,resource_id,department); self.allocations.append(row)
  if PRESERVE_AUDIT:self.audit.append(('resource_allocated',actor,task_id)); return row
 def communicate(self,actor,channel,message,department):
  self.authorize(actor,'POST','/messages',{'channel','message','department'},department); row={'actor':actor,'channel':channel,'message':message,'department':department}; self.messages.append(row); return row
 def performance_report(self,actor,department):
  self.authorize(actor,'GET','/performance',{'department'},department); report={'department':department,'open_tasks':sum(t['department']==department and t['status']=='open' for t in self.tasks.values()),'allocations':sum(a[2]==department for a in self.allocations)}; self.reports.append(report); return report
 def visible_actions(self,actor):
  user=self.users[actor]; return sorted(path for (method,path),spec in ENDPOINTS.items() if user['role'] in spec['roles'])
