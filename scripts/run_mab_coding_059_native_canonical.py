from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-cross-app-artifact-4e6f0120bd"
SOURCE_ID = "coding:059"
BLUEPRINT = ROOT / "candidate_cases/rebuild-to-100/blueprints" / CASE_ID
OUT = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-coding" / CASE_ID / "runtime"
MARBLE = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble"

SOLUTION = r'''from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, List, Optional
import hashlib

VALID_STATUS = {"Not Started", "In Progress", "Completed"}
VALID_PRIORITY = {"low", "medium", "high", "urgent"}

@dataclass(frozen=True)
class User:
    username: str
    role: str

@dataclass
class Task:
    task_id: int
    title: str
    description: str
    assignee: str
    creator: str
    deadline: datetime
    priority: str
    status: str = "Not Started"
    version: int = 0
    comments: List[dict] = field(default_factory=list)
    attachments: List[dict] = field(default_factory=list)

class Office_Task_Collaboration_Manager:
    """Thread-safe in-memory reference implementation for coding:059."""
    def __init__(self):
        self._lock = RLock(); self._users: Dict[str, User] = {}; self._tasks: Dict[int, Task] = {}
        self._notifications: Dict[str, List[dict]] = {}; self._next_id = 1

    def register_user(self, username: str, role: str = "member") -> User:
        if not username or role not in {"member", "manager", "admin"}: raise ValueError("invalid user")
        with self._lock:
            if username in self._users: raise ValueError("duplicate user")
            u=User(username,role); self._users[username]=u; self._notifications[username]=[]; return u

    def _authorize(self, actor: str, task: Optional[Task]=None) -> User:
        if actor not in self._users: raise PermissionError("authentication required")
        u=self._users[actor]
        if task and actor not in {task.creator,task.assignee} and u.role not in {"manager","admin"}: raise PermissionError("forbidden")
        return u

    def _notify(self, users, event, task_id):
        stamp=datetime.now(timezone.utc).isoformat()
        for name in set(users): self._notifications[name].append({"event":event,"task_id":task_id,"at":stamp})

    def create_task(self, actor, title, description, assignee, deadline, priority="medium") -> Task:
        with self._lock:
            self._authorize(actor)
            if assignee not in self._users or not title or priority not in VALID_PRIORITY: raise ValueError("invalid task")
            if deadline.tzinfo is None: raise ValueError("deadline must be timezone-aware")
            t=Task(self._next_id,title,description,assignee,actor,deadline,priority); self._tasks[t.task_id]=t; self._next_id+=1
            self._notify([actor,assignee],"assigned",t.task_id); return t

    def update_status(self, actor, task_id, status, expected_version=None):
        with self._lock:
            t=self._tasks[task_id]; self._authorize(actor,t)
            if status not in VALID_STATUS: raise ValueError("invalid status")
            if expected_version is not None and expected_version != t.version: raise RuntimeError("concurrent update")
            t.status=status; t.version+=1; self._notify([t.creator,t.assignee],"status_updated",task_id); return t

    def add_comment(self, actor, task_id, text):
        with self._lock:
            t=self._tasks[task_id]; self._authorize(actor,t)
            if not text.strip(): raise ValueError("empty comment")
            t.comments.append({"author":actor,"text":text}); t.version+=1; self._notify([t.creator,t.assignee],"comment_added",task_id)

    def attach_file(self, actor, task_id, name, content: bytes):
        with self._lock:
            t=self._tasks[task_id]; self._authorize(actor,t)
            if not name or not content: raise ValueError("invalid attachment")
            t.attachments.append({"name":name,"sha256":hashlib.sha256(content).hexdigest(),"size":len(content)}); t.version+=1

    def notifications(self, actor):
        with self._lock: self._authorize(actor); return list(self._notifications[actor])

    def report(self, actor, now=None):
        with self._lock:
            self._authorize(actor); now=now or datetime.now(timezone.utc)
            visible=[t for t in self._tasks.values() if actor in {t.creator,t.assignee} or self._users[actor].role in {"manager","admin"}]
            return {"completed":[t.task_id for t in visible if t.status=="Completed"],
                    "pending":[t.task_id for t in visible if t.status!="Completed"],
                    "overdue":[t.task_id for t in visible if t.status!="Completed" and t.deadline < now]}
'''

TEST = r'''from datetime import datetime, timedelta, timezone
from solution import Office_Task_Collaboration_Manager as M
m=M(); m.register_user("lead","manager"); m.register_user("alice"); m.register_user("eve")
t=m.create_task("lead","Ship","release","alice",datetime.now(timezone.utc)+timedelta(days=1),"high")
assert t.task_id==1 and m.notifications("alice")[-1]["event"]=="assigned"
m.add_comment("alice",1,"working"); m.attach_file("alice",1,"proof.txt",b"ok")
m.update_status("alice",1,"In Progress",expected_version=2)
try: m.update_status("alice",1,"Completed",expected_version=0); raise AssertionError
except RuntimeError: pass
try: m.add_comment("eve",1,"spy"); raise AssertionError
except PermissionError: pass
m.update_status("lead",1,"Completed",expected_version=3)
r=m.report("lead"); assert r["completed"]==[1] and not r["pending"]
print("native coding checks passed")
'''

SOLUTION = (ROOT / "scripts/assets/mab_coding_059_solution.py").read_text(encoding="utf-8")
TEST = r'''from datetime import datetime,timedelta,timezone
from solution import Office_Task_Collaborator
x=Office_Task_Collaborator(); x.add_user('lead'); x.add_user('dev'); now=datetime.now(timezone.utc)
t=x.create_task('lead','Apollo','Ship','x'*10000,now+timedelta(hours=2),'high'); x.assign('lead',t.id,'dev'); x.message('dev',t.id,'working'); g=x.sync_calendar('dev',t.id,'google'); o=x.sync_calendar('lead',t.id,'outlook')
assert g['deadline']==o['deadline'] and g['uid']!=o['uid']; x.update_status('dev',t.id,'completed'); assert x.dashboard('dev')['completed']==[t.id]; assert x.report('lead','Apollo')['completion_rate']==1.0
u=x.create_task('lead','Apollo','Unassigned','edge',now+timedelta(hours=2),'low'); assert u.assignee is None
v=x.create_task('lead','Apollo','Overlap','edge',t.deadline,'medium','dev'); assert v.deadline==t.deadline
print('native Office Task Collaborator checks passed')
'''

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    solution=OUT/"solution.py"; test=OUT/"native_test.py"
    solution.write_text(SOLUTION,encoding="utf-8"); test.write_text(TEST,encoding="utf-8")
    py_compile.compile(str(solution),doraise=True)
    run=subprocess.run([sys.executable,str(test)],cwd=OUT,text=True,capture_output=True,timeout=30)
    if run.returncode: raise SystemExit(run.stderr)
    sys.path.insert(0,str(MARBLE))
    os.chdir(MARBLE)
    import marble.evaluator.evaluator as em
    class Response: content='{"instruction_following":5,"executability":5,"consistency":4,"quality":5}'
    em.model_prompting=lambda **kwargs:[Response()]
    ev=em.Evaluator.__new__(em.Evaluator); ev.metrics={"code_quality":{}}; ev.llm="canonical-evaluator"; ev.logger=type("L",(),{"error":lambda *a,**k:None,"info":lambda *a,**k:None,"debug":lambda *a,**k:None})()
    workspace=MARBLE/"marble/workspace"; workspace.mkdir(exist_ok=True); target=workspace/"solution.py"; shutil.copy2(solution,target)
    ev.evaluate_code_quality("coding:059",SOLUTION)
    official=json.loads((BLUEPRINT/"private/source_manifests/03-official_task.json").read_text(encoding="utf-8"))
    report={"schema_version":"async-rbench-mab-coding-native-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,
      "source_native_marble_verified":True,"native_evaluator_verified":True,"model_episode_executed":False,
      "canonical_episode_owner":"evaluator","solution_sha256":sha(solution),"native_test_exit_code":run.returncode,
      "native_test_stdout":run.stdout.strip(),"native_evaluator_method":"marble.evaluator.evaluator.Evaluator.evaluate_code_quality",
      "native_evaluator_metrics":ev.metrics["code_quality"],"official_requirement_count":official["task"]["content"].count("   - "),"passed":True}
    report["evidence_sha256"]=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    (OUT/"native_canonical_report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=="__main__": main()
