DOMAIN='team_sync_sports'
ENFORCE_AVAILABILITY = True
PRESERVE_PERFORMANCE = True
EVENT_SCHEMA='player_profile_v2'
class TeamSync:
 def __init__(self): self.players={}; self.email_to_id={}; self.events={}; self.announcements=[]; self.performance={}; self.history=[]
 def create_player(self,player_id,email,role,availability):
  if role not in {'coach','player'} or player_id in self.players: raise ValueError('invalid profile')
  self.players[player_id]={'email':email,'role':role,'availability':list(availability),'active':True}; self.email_to_id[email]=player_id
 def schedule(self,event_id,start,end,attendees):
  if any(pid not in self.players for pid in attendees): raise ValueError('unknown player')
  if ENFORCE_AVAILABILITY:
   for pid in attendees:
    if not any(a<=start and end<=b for a,b in self.players[pid]['availability']): raise ValueError('unavailable player')
   for event in self.events.values():
    if set(attendees)&set(event['attendees']) and max(start,event['start'])<min(end,event['end']): raise ValueError('schedule conflict')
  self.events[event_id]={'start':start,'end':end,'attendees':list(attendees),'completed':False}; return self.events[event_id]
 def announce(self,actor,message,target='team'):
  if self.players[actor]['role']!='coach' and target=='team': raise PermissionError('coach required')
  self.announcements.append({'actor':actor,'message':message,'target':target})
 def record_performance(self,player_id,metric,value): self.performance.setdefault(player_id,[]).append((metric,value))
 def delete_profile(self,player_id):
  self.players[player_id]['active']=False
  for event in self.events.values():
   if not event['completed']: event['attendees']=[p for p in event['attendees'] if p!=player_id]
  if not PRESERVE_PERFORMANCE: self.performance.pop(player_id,None)
  self.history.append(('profile_deleted',player_id))
