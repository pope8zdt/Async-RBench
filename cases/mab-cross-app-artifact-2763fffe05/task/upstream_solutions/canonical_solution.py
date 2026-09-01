from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, List
import hashlib

@dataclass(frozen=True)
class User:
    username: str
    role: str

@dataclass
class Revision:
    number: int
    author: str
    markdown: str
    created_at: str
    parent: int | None

@dataclass
class Project:
    project_id: int
    title: str
    owner: str
    members: Dict[str, str]
    revisions: List[Revision] = field(default_factory=list)
    collaboration_log: List[dict] = field(default_factory=list)
    publication_state: str = "draft"

class BookSynergy:
    """Thread-safe reference backend for collaborative reference books."""
    def __init__(self):
        self._lock=RLock(); self._users={}; self._tokens={}; self._projects={}; self._next=1; self._subscribers={}

    def register(self, username, password, role="author"):
        if not username or len(password)<8 or role not in {"author","reviewer","publisher","admin"}: raise ValueError("invalid account")
        with self._lock:
            if username in self._users: raise ValueError("duplicate account")
            self._users[username]=(User(username,role),hashlib.sha256(password.encode()).hexdigest())

    def authenticate(self, username, password):
        with self._lock:
            item=self._users.get(username)
            if not item or item[1]!=hashlib.sha256(password.encode()).hexdigest(): raise PermissionError("bad credentials")
            token=hashlib.sha256(f"{username}:{len(self._tokens)}".encode()).hexdigest(); self._tokens[token]=username; return token

    def _actor(self, token):
        if token not in self._tokens: raise PermissionError("authentication required")
        return self._tokens[token]

    def create_project(self, token, title):
        with self._lock:
            actor=self._actor(token)
            if not title.strip(): raise ValueError("title required")
            p=Project(self._next,title,actor,{actor:"owner"}); self._projects[p.project_id]=p; self._next+=1; return p

    def add_member(self, token, project_id, username, permission="edit"):
        with self._lock:
            actor=self._actor(token); p=self._projects[project_id]
            if actor!=p.owner and self._users[actor][0].role!="admin": raise PermissionError("owner required")
            if username not in self._users or permission not in {"view","comment","edit","review","publish"}: raise ValueError("invalid member")
            p.members[username]=permission

    def commit(self, token, project_id, markdown, expected_parent=None):
        with self._lock:
            actor=self._actor(token); p=self._projects[project_id]
            if p.members.get(actor) not in {"owner","edit"}: raise PermissionError("edit denied")
            parent=p.revisions[-1].number if p.revisions else None
            if expected_parent!=parent: raise RuntimeError("revision conflict")
            r=Revision(len(p.revisions)+1,actor,markdown,datetime.now(timezone.utc).isoformat(),parent); p.revisions.append(r)
            event={"type":"revision","project_id":project_id,"revision":r.number,"author":actor}; p.collaboration_log.append(event)
            for callback in self._subscribers.get(project_id,[]): callback(dict(event))
            return r

    def subscribe(self, token, project_id, callback):
        actor=self._actor(token); p=self._projects[project_id]
        if actor not in p.members: raise PermissionError("membership required")
        self._subscribers.setdefault(project_id,[]).append(callback)

    def render(self, token, project_id, wysiwyg=False):
        actor=self._actor(token); p=self._projects[project_id]
        if actor not in p.members: raise PermissionError("view denied")
        text=p.revisions[-1].markdown if p.revisions else ""
        return {"markdown":text,"wysiwyg_html":text.replace("**","<strong>") if wysiwyg else None}

    def export_integration(self, token, project_id, provider, large_file: bytes=b""):
        actor=self._actor(token); p=self._projects[project_id]
        if p.members.get(actor) not in {"owner","publish"}: raise PermissionError("publish denied")
        if provider not in {"github","proofreader"}: raise ValueError("unsupported provider")
        return {"provider":provider,"revision":p.revisions[-1].number,"large_file_sha256":hashlib.sha256(large_file).hexdigest()}
