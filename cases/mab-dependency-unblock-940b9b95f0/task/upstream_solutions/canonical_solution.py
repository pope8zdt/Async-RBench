DOMAIN='matp'
APPLY_REALTIME_SNAPSHOT = True
PRESERVE_FEEDBACK = True
EVENT_SCHEMA='conditions_snapshot_v3'
class MATP:
 def __init__(self): self.feedback=[]; self.accepted=[]
 def rank(self,routes,preferences,snapshot,now):
  fresh=APPLY_REALTIME_SNAPSHOT and now-snapshot['observed_at']<=300; scored=[]
  for route in routes:
   time=route['minutes']; cost=route['cost']; carbon=route['carbon']; allowed=True
   if fresh:
    time+=snapshot['transit_delays'].get(route['mode'],0); speed=snapshot['traffic_speeds'].get(route['mode'])
    if speed: time*=max(1,30/speed)
    if route['mode'] in snapshot['weather_restrictions']: allowed=False
   if allowed:scored.append({**route,'adjusted_minutes':round(time,2),'adjusted_cost':cost,'adjusted_carbon':carbon})
  return {'fastest':sorted(scored,key=lambda r:(r['adjusted_minutes'],r['id'])),'cheapest':sorted(scored,key=lambda r:(r['adjusted_cost'],r['id'])),'greenest':sorted(scored,key=lambda r:(r['adjusted_carbon'],r['id'])),'selected':sorted(scored,key=lambda r:(r['adjusted_minutes']*preferences.get('time',1)+r['adjusted_cost']*preferences.get('cost',1)+r['adjusted_carbon']*preferences.get('carbon',1),r['id']))[0]}
 def report(self,user,route_id,issue,rating):
  if PRESERVE_FEEDBACK:self.feedback.append({'user':user,'route_id':route_id,'issue':issue,'rating':rating})
 def accept(self,user,route): self.accepted.append((user,route['id']))
