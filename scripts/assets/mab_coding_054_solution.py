from dataclasses import dataclass,field
from threading import RLock
@dataclass
class Match:
 teams:dict; points:dict=field(default_factory=dict); seq:int=0; score:dict=field(default_factory=dict)
class GalacticConquest:
 def __init__(self): self.lock=RLock(); self.characters={}; self.ai_ready=False; self.map_ready=False; self.multiplayer_ready=False; self.matches={}; self.next_id=1
 def create_character(self,user,name,abilities):
  if not name or not 1<=len(set(abilities))<=3: raise ValueError('abilities')
  self.characters[user]={'name':name,'abilities':tuple(abilities),'xp':0}
 def configure_ai(self,policy):
  if not self.characters or policy not in {'adaptive','defensive','aggressive'}: raise RuntimeError('character dependency')
  self.ai_ready=True; self.ai_policy=policy
 def generate_map(self,key_points,destructible=True,powerups=True):
  if not self.ai_ready or key_points<2: raise RuntimeError('ai dependency')
  self.map_ready=True; self.map={'key_points':key_points,'destructible':destructible,'powerups':powerups}
 def enable_multiplayer(self):
  if not (self.characters and self.ai_ready and self.map_ready): raise RuntimeError('core dependency')
  self.multiplayer_ready=True
 def start(self,teams):
  if not self.multiplayer_ready or len(teams)!=2 or any(not x for x in teams.values()): raise RuntimeError('multiplayer dependency')
  i=self.next_id; self.next_id+=1; self.matches[i]=Match(teams,{p:None for p in range(self.map['key_points'])},score={t:0 for t in teams}); return i
 def action(self,mid,team,kind,point,expected_sequence):
  with self.lock:
   m=self.matches[mid]
   if expected_sequence!=m.seq: raise RuntimeError('stale action')
   if team not in m.teams or kind not in {'capture','defend','chat'}: raise ValueError('action')
   if kind=='capture': m.points[point]=team; m.score[team]+=10
   elif kind=='defend' and m.points[point]==team: m.score[team]+=3
   m.seq+=1; return {'sequence':m.seq,'team':team,'kind':kind}
 def finish(self,mid,winner):
  m=self.matches[mid]
  if winner not in m.teams: raise ValueError('winner')
  for u in m.teams[winner]: self.characters[u]['xp']+=100
  return {'winner':winner,'score':dict(m.score),'sequence':m.seq}
