DOMAIN='music_mashup_battle'
ORDERED_EVENTS = True
PRESERVE_ROOM_HISTORY = True
EVENT_SCHEMA='mashup_room_events_v3'
class MusicMashupBattle:
 def __init__(self): self.rooms={}; self.votes={}; self.scores={}
 def create_room(self,rid,owner,private=False): self.rooms[rid]={'private':private,'participants':{owner},'sequence':0,'edits':[],'playback':0,'chat':[],'history':[]}
 def apply_event(self,rid,event):
  room=self.rooms[rid]; expected=room['sequence']+1
  if ORDERED_EVENTS and event['sequence']!=expected:return {'status':'resync_required','expected':expected}
  kind=event['type']; actor=event['actor']
  if kind=='join':room['participants'].add(actor)
  elif kind=='leave':room['participants'].discard(actor)
  elif kind=='edit':room['edits'].append({'actor':actor,'operation':event['operation'],'sequence':event['sequence']})
  elif kind=='playback':room['playback']=event['position']
  elif kind=='chat':room['chat'].append((actor,event['message']))
  room['sequence']=event['sequence']
  if PRESERVE_ROOM_HISTORY:room['history'].append(dict(event))
  return {'status':'applied','sequence':room['sequence']}
 def vote(self,user,mashup,value):
  key=(user,mashup)
  if key in self.votes:return {'status':'duplicate','score':self.scores.get(mashup,0)}
  self.votes[key]=value; self.scores[mashup]=self.scores.get(mashup,0)+value; return {'status':'accepted','score':self.scores[mashup]}
 def leaderboard(self):return sorted(self.scores.items(),key=lambda x:(-x[1],x[0]))
