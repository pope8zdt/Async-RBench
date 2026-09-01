from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
import hashlib

@dataclass
class Task:
    id:int; project:str; title:str; description:str; deadline:datetime; priority:str; creator:str; assignee:str|None=None; status:str="not started"; messages:list=field(default_factory=list)

class Office_Task_Collaborator:
    def __init__(self):
        self._lock=RLock(); self.users=set(); self.tasks={}; self.calendar_events={}; self.next_id=1
    def add_user(self,user):
        if not user: raise ValueError("user required")
        self.users.add(user)
    def create_task(self,actor,project,title,description,deadline,priority="medium",assignee=None):
        if actor not in self.users: raise PermissionError("unknown user")
        if assignee is not None and assignee not in self.users: raise ValueError("unknown assignee")
        if deadline.tzinfo is None or priority not in {"low","medium","high","urgent"}: raise ValueError("invalid task")
        with self._lock:
            t=Task(self.next_id,project,title,description,deadline,priority,actor,assignee); self.tasks[t.id]=t; self.next_id+=1; return t
    def assign(self,actor,task_id,assignee):
        with self._lock:
            t=self.tasks[task_id]
            if actor!=t.creator or assignee not in self.users: raise PermissionError("creator required")
            t.assignee=assignee
    def update_status(self,actor,task_id,status):
        with self._lock:
            t=self.tasks[task_id]
            if actor not in {t.creator,t.assignee}: raise PermissionError("task access required")
            if status not in {"not started","in progress","completed"}: raise ValueError("invalid status")
            t.status=status
    def message(self,actor,task_id,text):
        t=self.tasks[task_id]
        if actor not in {t.creator,t.assignee} or not text.strip(): raise PermissionError("task access required")
        t.messages.append({"author":actor,"text":text})
    def sync_calendar(self,actor,task_id,provider):
        t=self.tasks[task_id]
        if actor not in {t.creator,t.assignee} or provider not in {"google","outlook"}: raise PermissionError("calendar access denied")
        uid=hashlib.sha256(f"{provider}:{task_id}:{t.deadline.isoformat()}".encode()).hexdigest()
        event={"uid":uid,"provider":provider,"task_id":task_id,"deadline":t.deadline.isoformat(),"reminder_minutes":30}; self.calendar_events[(provider,task_id)]=event; return dict(event)
    def dashboard(self,user,now=None):
        if user not in self.users: raise PermissionError("unknown user")
        now=now or datetime.now(timezone.utc); assigned=[t for t in self.tasks.values() if t.assignee==user]
        return {"assigned":[t.id for t in assigned],"upcoming":[t.id for t in assigned if t.status!="completed" and t.deadline>=now],"completed":[t.id for t in assigned if t.status=="completed"]}
    def report(self,actor,project):
        if actor not in self.users: raise PermissionError("unknown user")
        ts=[t for t in self.tasks.values() if t.project==project]; done=[t for t in ts if t.status=="completed"]
        by_user={u:{"assigned":0,"completed":0} for u in self.users}
        for t in ts:
            if t.assignee: by_user[t.assignee]["assigned"]+=1; by_user[t.assignee]["completed"]+=int(t.status=="completed")
        return {"project":project,"total":len(ts),"completed":len(done),"completion_rate":len(done)/len(ts) if ts else 0.0,"team":by_user}
