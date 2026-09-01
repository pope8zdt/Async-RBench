DOMAIN='travel_collaborator'
VALIDATE_SESSIONS = True
PRESERVE_COMMUNICATION = True
EVENT_SCHEMA='travel_auth_v2'
class TravelCollaborator:
 def __init__(self): self.users={}; self.sessions={}; self.itineraries={}; self.chat=[]; self.reviews=[]
 def register(self,user,password,private=False): self.users[user]={'password':'hash:'+password,'private':private,'profile':{'name':user}}
 def login(self,user,password,now,ttl=60):
  if self.users.get(user,{}).get('password')!='hash:'+password: raise PermissionError('bad login')
  token=f'{user}:{now}'; self.sessions[token]={'user':user,'expires':now+ttl}; return token
 def actor(self,token,now):
  if not VALIDATE_SESSIONS:return token.split(':')[0]
  session=self.sessions.get(token)
  if not session or now>=session['expires']:raise PermissionError('expired or forged session')
  return session['user']
 def create_itinerary(self,token,now,iid):
  user=self.actor(token,now); self.itineraries[iid]={'roles':{user:'owner'},'items':[],'comments':[]}; return iid
 def invite(self,token,now,iid,user,role):
  actor=self.actor(token,now)
  if self.itineraries[iid]['roles'].get(actor)!='owner' or role not in {'contributor','viewer'}:raise PermissionError('owner required')
  self.itineraries[iid]['roles'][user]=role
 def add_item(self,token,now,iid,item):
  user=self.actor(token,now)
  if self.itineraries[iid]['roles'].get(user) not in {'owner','contributor'}:raise PermissionError('write denied')
  self.itineraries[iid]['items'].append(item)
 def comment(self,token,now,iid,text):
  user=self.actor(token,now)
  if user not in self.itineraries[iid]['roles']:raise PermissionError('not invited')
  if PRESERVE_COMMUNICATION:self.itineraries[iid]['comments'].append((user,text)); self.chat.append((iid,user,text))
 def profile(self,viewer,target):
  if self.users[target]['private'] and viewer!=target:return {'name':'private'}
  return dict(self.users[target]['profile'])
