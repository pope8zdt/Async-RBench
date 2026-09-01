from __future__ import annotations
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List
import hashlib

@dataclass
class Quest:
    quest_id:int; title:str; owner:str; status:str="open"; version:int=0; collaborators:set=field(default_factory=set)
@dataclass
class SkillPlan:
    plan_id:int; character:str; owner:str; skills:Dict[str,int]=field(default_factory=dict); version:int=0; collaborators:set=field(default_factory=set)

class QuestHub:
    """Thread-safe quest/skill synchronization backend for coding:070."""
    def __init__(self):
        self._lock=RLock(); self._users={}; self._tokens={}; self._quests={}; self._plans={}; self._events=[]; self._subs={}; self._next_q=1; self._next_p=1
    def register(self,user,password):
        if not user or len(password)<8: raise ValueError("invalid account")
        with self._lock:
            if user in self._users: raise ValueError("duplicate")
            self._users[user]=hashlib.sha256(password.encode()).hexdigest()
    def login(self,user,password,device):
        if not device: raise ValueError("device required")
        with self._lock:
            if self._users.get(user)!=hashlib.sha256(password.encode()).hexdigest(): raise PermissionError("bad credentials")
            token=hashlib.sha256(f"{user}:{device}:{len(self._tokens)}".encode()).hexdigest(); self._tokens[token]=(user,device); return token
    def _actor(self,token):
        if token not in self._tokens: raise PermissionError("authentication required")
        return self._tokens[token][0]
    def subscribe(self,token,resource,callback): self._actor(token); self._subs.setdefault(resource,[]).append(callback)
    def _emit(self,resource,kind,version):
        event={"resource":resource,"kind":kind,"version":version,"sequence":len(self._events)+1}; self._events.append(event)
        for cb in self._subs.get(resource,[]): cb(dict(event))
    def create_quest(self,token,title):
        with self._lock:
            actor=self._actor(token); q=Quest(self._next_q,title,actor,collaborators={actor}); self._quests[q.quest_id]=q; self._next_q+=1; self._emit(f"quest:{q.quest_id}","created",q.version); return q
    def share_quest(self,token,qid,user):
        with self._lock:
            actor=self._actor(token); q=self._quests[qid]
            if actor!=q.owner or user not in self._users: raise PermissionError("owner required")
            q.collaborators.add(user)
    def update_quest(self,token,qid,status,expected_version):
        if status not in {"open","active","completed"}: raise ValueError("invalid status")
        with self._lock:
            actor=self._actor(token); q=self._quests[qid]
            if actor not in q.collaborators: raise PermissionError("collaboration required")
            if expected_version!=q.version: raise RuntimeError("quest version conflict")
            q.status=status; q.version+=1; self._emit(f"quest:{qid}","updated",q.version); return q
    def create_skill_plan(self,token,character):
        with self._lock:
            actor=self._actor(token); p=SkillPlan(self._next_p,character,actor,collaborators={actor}); self._plans[p.plan_id]=p; self._next_p+=1; return p
    def share_plan(self,token,pid,user):
        with self._lock:
            actor=self._actor(token); p=self._plans[pid]
            if actor!=p.owner or user not in self._users: raise PermissionError("owner required")
            p.collaborators.add(user)
    def set_skill(self,token,pid,skill,level,expected_version):
        if not skill or not 0<=level<=100: raise ValueError("invalid skill")
        with self._lock:
            actor=self._actor(token); p=self._plans[pid]
            if actor not in p.collaborators: raise PermissionError("collaboration required")
            if expected_version!=p.version: raise RuntimeError("plan version conflict")
            p.skills[skill]=level; p.version+=1; self._emit(f"plan:{pid}","skill_updated",p.version); return p
    def sync_since(self,token,sequence): self._actor(token); return [dict(e) for e in self._events if e["sequence"]>sequence]
