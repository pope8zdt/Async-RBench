DOMAIN='multi_agent_maze'
EVENT_SCHEMA='maze_transition_protocol_v2'
ENFORCE_AUTHORITY_TRANSITIONS = True
PRESERVE_MAZE_HISTORY = True
from collections import deque
class MultiAgentMaze:
 def __init__(self,width,height,walls=(),exit_cell=None,difficulty='medium'):
  self.width=width; self.height=height; self.walls=set(map(tuple,walls)); self.exit=tuple(exit_cell or (width-1,height-1)); self.difficulty=difficulty; self.players={}; self.blocks={}; self.messages=[]; self.history=[]; self.saved={}; self.tutorial={}; self.achievements=set(); self.version=0; self.protocol=None
 def add_player(self,player_id,role,position):
  if role not in {'scout','builder','navigator'}: raise ValueError('invalid role')
  self.players[player_id]={'role':role,'position':tuple(position)}; self.tutorial[player_id]=set(); return self.players[player_id]
 def add_block(self,block_id,position): self.blocks[block_id]=tuple(position)
 def apply_transition_protocol(self,protocol):
  if protocol.get('collision_policy')!='reject_occupied_destination' or not protocol.get('requires_expected_version'): raise ValueError('invalid protocol')
  self.protocol=dict(protocol); return self.protocol
 def _authorize(self,player_id,action,expected_version):
  if ENFORCE_AUTHORITY_TRANSITIONS:
   if not self.protocol: raise RuntimeError('transition dependency unresolved')
   if expected_version!=self.version: raise RuntimeError('stale maze version')
   if action not in self.protocol['roles'][self.players[player_id]['role']]: raise PermissionError('role cannot perform action')
 def _free(self,pos,ignore_block=None):
  p=tuple(pos); occupied=set(self.walls)|{v for k,v in self.blocks.items() if k!=ignore_block}|{v['position'] for v in self.players.values()}
  return 0<=p[0]<self.width and 0<=p[1]<self.height and p not in occupied
 def move_block(self,player_id,block_id,destination,expected_version):
  self._authorize(player_id,'move_block',expected_version)
  if not self._free(destination,block_id): raise ValueError('occupied destination')
  before=self.blocks[block_id]; self.blocks[block_id]=tuple(destination); self.version+=1
  if PRESERVE_MAZE_HISTORY:self.history.append(('move_block',player_id,block_id,before,tuple(destination),self.version))
  return self.version
 def move_player(self,player_id,destination,expected_version):
  self._authorize(player_id,'move_player',expected_version)
  if not self._free(destination): raise ValueError('occupied destination')
  self.players[player_id]['position']=tuple(destination); self.version+=1
  if PRESERVE_MAZE_HISTORY:self.history.append(('move_player',player_id,tuple(destination),self.version))
  if tuple(destination)==self.exit:self.achievements.add((player_id,'maze_complete'))
  return self.version
 def message(self,player_id,text):
  row={'player':player_id,'text':text,'version':self.version}
  if PRESERVE_MAZE_HISTORY:self.messages.append(row)
  return row
 def path_exists(self,start):
  start=tuple(start); blocked=self.walls|set(self.blocks.values()); q=deque([start]); seen={start}
  while q:
   p=q.popleft()
   if p==self.exit:return True
   for n in ((p[0]+1,p[1]),(p[0]-1,p[1]),(p[0],p[1]+1),(p[0],p[1]-1)):
    if 0<=n[0]<self.width and 0<=n[1]<self.height and n not in blocked and n not in seen:seen.add(n); q.append(n)
  return False
 def complete_tutorial(self,player_id,step):
  if PRESERVE_MAZE_HISTORY:self.tutorial[player_id].add(step)
 def save_progress(self,key):
  snap={'players':{k:dict(v) for k,v in self.players.items()},'blocks':dict(self.blocks),'version':self.version,'achievements':set(self.achievements)}
  if PRESERVE_MAZE_HISTORY:self.saved[key]=snap
  return snap
 def load_progress(self,key): return self.saved[key]
