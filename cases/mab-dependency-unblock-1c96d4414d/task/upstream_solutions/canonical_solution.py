from __future__ import annotations
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List
import hashlib

@dataclass
class Team:
    users: Dict[str,str] = field(default_factory=dict)
    datasets: Dict[str,dict] = field(default_factory=dict)
    notes: List[dict] = field(default_factory=list)
    sequence: int = 0

class SportsTeamCollaborator:
    """Thread-safe, team-isolated sports analysis reference for coding:019."""
    def __init__(self, max_upload=10_000_000): self._lock=RLock(); self.teams={}; self.max_upload=max_upload
    def create_team(self, team_id):
        with self._lock:
            if not team_id or team_id in self.teams: raise ValueError('invalid team')
            self.teams[team_id]=Team()
    def add_user(self, team_id, user, role):
        if role not in {'coach','analyst','player'}: raise ValueError('invalid role')
        with self._lock: self.teams[team_id].users[user]=role
    def upload(self, team_id, actor, name, content:bytes, kind):
        with self._lock:
            t=self.teams[team_id]; role=t.users.get(actor)
            if role not in {'coach','analyst'}: raise PermissionError('upload forbidden')
            if kind not in {'video','csv','stream'} or not content or len(content)>self.max_upload: raise ValueError('invalid upload')
            digest=hashlib.sha256(content).hexdigest(); t.datasets[name]={'kind':kind,'sha256':digest,'size':len(content)}; return digest
    def metric(self, team_id, actor, player, samples):
        with self._lock:
            t=self.teams[team_id]
            if actor not in t.users or (t.users[actor]=='player' and actor!=player): raise PermissionError('metric forbidden')
            if not samples: raise ValueError('empty samples')
            return {'player':player,'average':sum(samples)/len(samples),'maximum':max(samples),'count':len(samples)}
    def collaborate(self, team_id, actor, channel, text, expected_sequence=None):
        with self._lock:
            t=self.teams[team_id]
            if actor not in t.users: raise PermissionError('unknown user')
            if channel not in {'note','comment','chat'} or not text.strip(): raise ValueError('invalid message')
            if expected_sequence is not None and expected_sequence!=t.sequence: raise RuntimeError('concurrent edit')
            t.sequence+=1; event={'sequence':t.sequence,'actor':actor,'channel':channel,'text':text}; t.notes.append(event); return event
    def report(self, team_id, actor):
        with self._lock:
            t=self.teams[team_id]
            if t.users.get(actor) not in {'coach','analyst'}: raise PermissionError('report forbidden')
            return {'dataset_count':len(t.datasets),'collaboration_events':list(t.notes),'sequence':t.sequence}
