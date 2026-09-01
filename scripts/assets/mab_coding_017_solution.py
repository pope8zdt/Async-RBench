from dataclasses import dataclass,field
@dataclass
class Player: name:str; role:str; points:int=0
@dataclass
class Game: level:int; grid:list; players:dict; history:list=field(default_factory=list); sequence:int=0; completed:bool=False
class MultiAgentMaze:
 def __init__(self): self.profiles={}; self.games={}; self.next=1; self.subs={}; self.metrics={}
 def register(self,name,role):
  if role not in {'pathfinder','blocker','swapper'}: raise ValueError('role'); self.profiles[name]=role
  self.profiles[name]=role
 def create_game(self,names,level=1):
  if set(self.profiles[n] for n in names)!={'pathfinder','blocker','swapper'}: raise ValueError('roles required')
  size=3+level; g=Game(level,[['.' for _ in range(size)] for _ in range(size)],{n:Player(n,self.profiles[n]) for n in names}); self.games[self.next]=g; self.next+=1; return g
 def subscribe(self,gid,cb): self.subs.setdefault(gid,[]).append(cb)
 def act(self,gid,name,action,row,col,target=None):
  g=self.games[gid]; p=g.players[name]
  allowed={'pathfinder':{'path'},'blocker':{'block','unblock'},'swapper':{'swap'}}
  if action not in allowed[p.role]: raise PermissionError('role action denied')
  if not (0<=row<len(g.grid) and 0<=col<len(g.grid)): raise ValueError('bounds')
  if action=='path': g.grid[row][col]='P'
  elif action=='block': g.grid[row][col]='#'
  elif action=='unblock': g.grid[row][col]='.'
  else:
   if target is None: raise ValueError('target'); r2,c2=target; g.grid[row][col],g.grid[r2][c2]=g.grid[r2][c2],g.grid[row][col]
  g.sequence+=1; p.points+=10; e={'sequence':g.sequence,'player':name,'role':p.role,'action':action}; g.history.append(e)
  for cb in self.subs.get(gid,[]): cb(dict(e))
  return e
 def complete(self,gid):
  g=self.games[gid]; g.completed=True; bonus=25 if len({e['role'] for e in g.history})==3 else 0
  for p in g.players.values(): p.points+=bonus; self.metrics[p.name]={'games':self.metrics.get(p.name,{}).get('games',0)+1,'points':p.points}
  return bonus
 def hint(self,gid):
  g=self.games[gid]; missing={'pathfinder','blocker','swapper'}-{e['role'] for e in g.history}; return 'Need action from '+','.join(sorted(missing)) if missing else 'Coordinate a safe path to the exit'
