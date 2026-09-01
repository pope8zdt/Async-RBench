DOMAIN='galactic_dominion'
EVENT_SCHEMA='galactic_common_threat_rulebook_v2'
USE_COMPLETE_EVENT_RULEBOOK = True
PRESERVE_DIPLOMACY_HISTORY = True
class GalacticDominion:
 def __init__(self): self.agents={}; self.turn_order=[]; self.turn=0; self.alliances=set(); self.communications=[]; self.events=[]; self.contract=None
 def add_agent(self,agent_id,capability,resources=100):
  if not agent_id or agent_id in self.agents or resources<0: raise ValueError('invalid agent')
  self.agents[agent_id]={'capability':capability,'resources':resources,'structures':[],'technologies':set(),'fleets':0,'territory':1,'economy':resources}; self.turn_order.append(agent_id)
 def apply_event_rulebook(self,contract):
  if contract.get('common_threat')!='alliance_required' or set(contract.get('score_weights',{}))!={'territory','technology','economy'}: raise ValueError('incomplete rulebook')
  self.contract=dict(contract); return self.contract
 def _actor(self,agent_id):
  if USE_COMPLETE_EVENT_RULEBOOK and self.turn_order[self.turn%len(self.turn_order)]!=agent_id: raise RuntimeError('not this agent turn')
  return self.agents[agent_id]
 def end_turn(self): self.turn+=1
 def build(self,agent_id,structure,cost):
  a=self._actor(agent_id)
  if cost<=0 or a['resources']<cost: raise ValueError('insufficient resources')
  a['resources']-=cost; a['structures'].append(structure); a['economy']+=cost//2; return structure
 def research(self,agent_id,technology,cost):
  a=self._actor(agent_id)
  if a['resources']<cost: raise ValueError('insufficient resources')
  a['resources']-=cost; a['technologies'].add(technology); return technology
 def commission_fleet(self,agent_id,cost):
  a=self._actor(agent_id)
  if a['resources']<cost: raise ValueError('insufficient resources')
  a['resources']-=cost; a['fleets']+=1
 def negotiate_alliance(self,a,b,terms):
  if a not in self.agents or b not in self.agents or a==b or not terms: raise ValueError('invalid alliance')
  pair=tuple(sorted((a,b))); self.alliances.add(pair)
  if PRESERVE_DIPLOMACY_HISTORY:self.communications.append({'agents':pair,'terms':terms})
  return pair
 def resolve_dynamic_event(self,event_id,event_type,participants):
  if USE_COMPLETE_EVENT_RULEBOOK and not self.contract: raise RuntimeError('event rulebook required')
  participants=tuple(sorted(participants))
  if event_type=='alien_invasion' and (len(participants)<2 or any(tuple(sorted((a,b))) not in self.alliances for i,a in enumerate(participants) for b in participants[i+1:])): raise RuntimeError('common threat requires alliance')
  for agent_id in participants:self.agents[agent_id]['territory']+=1
  row={'event_id':event_id,'type':event_type,'participants':participants,'resolved':True}; self.events.append(row); return row
 def adaptive_difficulty(self,agent_id):
  score=self.score(agent_id); low,high=self.contract['difficulty_bounds']; return max(low,min(high,1+score//100))
 def score(self,agent_id):
  a=self.agents[agent_id]; w=self.contract['score_weights']; return a['territory']*w['territory']+len(a['technologies'])*w['technology']+a['economy']*w['economy']
