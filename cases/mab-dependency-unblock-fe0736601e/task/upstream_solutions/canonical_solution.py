DOMAIN='collaborative_schedule_planner'
EVENT_SCHEMA='team_schedule_optimizer_v2'
USE_COMPLETE_OPTIMIZER = True
PRESERVE_SCHEDULE_HISTORY = True
class CollaborativeSchedulePlanner:
 def __init__(self): self.users={}; self.tasks={}; self.availability={}; self.feedback=[]; self.notifications=[]; self.schedules={}; self.reports=[]; self.contract=None
 def add_user(self,user_id,available_slots): self.users[user_id]={}; self.availability[user_id]=list(available_slots)
 def add_task(self,task_id,owner,name,duration,priority,dependencies=()):
  if owner not in self.users or duration<=0 or priority<1: raise ValueError('invalid task')
  self.tasks[task_id]={'owner':owner,'name':name,'duration':int(duration),'priority':int(priority),'dependencies':list(dependencies)}; return self.tasks[task_id]
 def apply_optimizer_contract(self,contract):
  if set(contract.get('constraints',[]))!={'availability','task_dependencies','no_overlap','priority','feedback'}: raise ValueError('incomplete optimizer')
  self.contract=dict(contract); return self.contract
 def edit_task(self,actor,task_id,**changes):
  self.tasks[task_id].update(changes)
  if PRESERVE_SCHEDULE_HISTORY:self.notifications.append({'actor':actor,'task_id':task_id,'changes':sorted(changes)})
 def provide_feedback(self,user_id,task_id,delta):
  self.tasks[task_id]['priority']=max(1,self.tasks[task_id]['priority']+int(delta)); row={'user':user_id,'task':task_id,'delta':int(delta)}
  if PRESERVE_SCHEDULE_HISTORY:self.feedback.append(row)
  return row
 def _topological(self):
  pending=set(self.tasks); done=[]
  while pending:
   ready=[t for t in pending if set(self.tasks[t]['dependencies'])<=set(done)]
   if not ready: raise ValueError('dependency cycle')
   ready.sort(key=lambda t:(-self.tasks[t]['priority'],t)); done.extend(ready); pending-=set(ready)
  return done
 def optimize(self):
  if USE_COMPLETE_OPTIMIZER and not self.contract: raise RuntimeError('optimizer incomplete')
  occupied={u:set() for u in self.users}; schedule={}
  for tid in self._topological():
   t=self.tasks[tid]; slots=sorted(self.availability[t['owner']]); needed=(t['duration']+29)//30; start=None
   for i in range(len(slots)-needed+1):
    block=slots[i:i+needed]
    if block==list(range(block[0],block[0]+needed)) and not occupied[t['owner']].intersection(block): start=block; break
   if start is None: raise RuntimeError('no feasible slot')
   schedule[tid]={'owner':t['owner'],'start_slot':start[0],'end_slot':start[-1]+1,'priority':t['priority']}; occupied[t['owner']].update(start)
  self.schedules=schedule; return schedule
 def report(self):
  rows=[{'task_id':t,**v} for t,v in sorted(self.schedules.items(),key=lambda x:x[1]['start_slot'])]; usage={u:sum(v['end_slot']-v['start_slot'] for v in self.schedules.values() if v['owner']==u)*30 for u in self.users}; report={'gantt':rows,'minutes_by_user':usage}
  if PRESERVE_SCHEDULE_HISTORY:self.reports.append(report)
  return report
