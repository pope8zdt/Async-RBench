DOMAIN='multi_agent_drift_championship'
EVENT_SCHEMA='drift_physics_v2'
USE_RETURNED_PHYSICS = True
PRESERVE_RACE_HISTORY = True

class DriftChampionship:
 def __init__(self):
  self.agents={}; self.tracks={}; self.replays=[]; self.feedback=[]; self.history=[]
 def add_agent(self,agent_id,handling,drift_capability,style=1.0):
  if agent_id in self.agents or handling<=0 or drift_capability<=0: raise ValueError('invalid agent')
  self.agents[agent_id]={'handling':float(handling),'drift_capability':float(drift_capability),'style':float(style)}
 def add_track(self,track_id,grip,difficulty,obstacles=()):
  if not 0<grip<=1: raise ValueError('invalid grip')
  self.tracks[track_id]={'grip':float(grip),'difficulty':difficulty,'obstacles':tuple(obstacles)}
 def step(self,agent_id,track_id,state,steering,throttle,dt=0.1,grip_multiplier=1.0,collision=False):
  agent=self.agents[agent_id]; track=self.tracks[track_id]; grip=max(0.0,min(1.0,track['grip']*grip_multiplier))
  if USE_RETURNED_PHYSICS:
   angle=round(float(state.get('angle',0))+steering*agent['handling']*grip*dt*40,4)
   speed=round(max(0.0,float(state.get('speed',0))+throttle*dt*8-grip*abs(steering)*dt),4)
  else:
   angle=round(float(state.get('angle',0))+steering,4); speed=round(float(state.get('speed',0))+throttle,4)
  drifting=abs(angle)>=10 and speed>=5 and not collision
  combo=0.0 if collision or not drifting else round(float(state.get('combo_duration',0))+dt,4)
  score=0.0 if not drifting else round(abs(angle)*speed*agent['style']*agent['drift_capability']*combo*grip,3)
  event={'agent_id':agent_id,'track_id':track_id,'dt':dt,'angle':angle,'speed':speed,'surface_grip':grip,'collision':bool(collision),'combo_duration':combo,'drift_score':score}
  if PRESERVE_RACE_HISTORY: self.history.append(dict(event))
  return event
 def strategy(self,agent_id,own_score,opponent_scores,surface_grip):
  if surface_grip<0.6: action='grip_conserve'
  elif opponent_scores and max(opponent_scores)>own_score*1.2: action='defensive_line'
  else: action='attack_line'
  result={'agent_id':agent_id,'action':action,'surface_grip':surface_grip}; self.feedback.append(result); return result
 def save_replay(self,race_id,events):
  if PRESERVE_RACE_HISTORY: self.replays.append({'race_id':race_id,'events':list(events)})
  return race_id
