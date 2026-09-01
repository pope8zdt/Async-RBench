DOMAIN='cultural_exchange_hub'
EVENT_SCHEMA='cultural_exchange_dependency_v2'
ENFORCE_MODULE_DEPENDENCIES = True
PRESERVE_CULTURAL_ACTIVITY = True
class CulturalExchangeHub:
 def __init__(self): self.profiles={}; self.tours={}; self.tour_visits=[]; self.language_sessions=[]; self.workshops={}; self.discussions=[]; self.ratings=[]; self.contract=None
 def apply_dependency_contract(self,contract):
  if contract.get('order')!=['profiles','virtual_tours','language_exchange','workshops','feedback']: raise ValueError('invalid module order')
  self.contract=dict(contract); return self.contract
 def register(self,user_id,background,interests,profile_picture):
  if not all([user_id,background,interests,profile_picture]): raise ValueError('complete profile required')
  self.profiles[user_id]={'background':background,'interests':list(interests),'profile_picture':profile_picture}; return self.profiles[user_id]
 def add_tour(self,tour_id,landmark,hotspots,audio_guide): self.tours[tour_id]={'landmark':landmark,'hotspots':dict(hotspots),'audio_guide':audio_guide}
 def visit_tour(self,user_id,tour_id,hotspot):
  if ENFORCE_MODULE_DEPENDENCIES and (not self.contract or user_id not in self.profiles): raise RuntimeError('profile dependency unresolved')
  info=self.tours[tour_id]['hotspots'][hotspot]
  if PRESERVE_CULTURAL_ACTIVITY:self.tour_visits.append((user_id,tour_id,hotspot))
  return {'info':info,'audio':self.tours[tour_id]['audio_guide']}
 def language_exchange(self,a,b,language,text):
  if ENFORCE_MODULE_DEPENDENCIES and not any(v[0] in {a,b} for v in self.tour_visits): raise RuntimeError('tour dependency unresolved')
  translated=f'[{language}] {text}'; row={'users':tuple(sorted((a,b))),'language':language,'text':text,'translation':translated}
  if PRESERVE_CULTURAL_ACTIVITY:self.language_sessions.append(row)
  return row
 def add_workshop(self,workshop_id,expert,mode):
  if mode not in {'live','recorded'}: raise ValueError('invalid mode')
  self.workshops[workshop_id]={'expert':expert,'mode':mode,'participants':set(),'questions':[]}
 def join_workshop(self,user_id,workshop_id,question=None):
  if ENFORCE_MODULE_DEPENDENCIES and not any(user_id in s['users'] for s in self.language_sessions): raise RuntimeError('language dependency unresolved')
  w=self.workshops[workshop_id]; w['participants'].add(user_id)
  if question:w['questions'].append((user_id,question)); self.discussions.append((workshop_id,user_id,question))
 def rate(self,user_id,module_id,score,review):
  experienced=any(v[0]==user_id and v[1]==module_id for v in self.tour_visits) or (module_id in self.workshops and user_id in self.workshops[module_id]['participants'])
  if ENFORCE_MODULE_DEPENDENCIES and (not experienced or not 1<=score<=5): raise PermissionError('completed experience required')
  row={'user':user_id,'module':module_id,'score':score,'review':review}; self.ratings.append(row); return row
