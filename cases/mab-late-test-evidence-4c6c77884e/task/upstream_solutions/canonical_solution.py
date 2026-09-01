DOMAIN='family_code_quest'
EVENT_SCHEMA='family_code_quest_tests_v2'
APPLY_UNIQUE_TEST_EVIDENCE = True
PRESERVE_COLLABORATION_STATE = True

class FamilyCodeQuest:
 def __init__(self):
  self.users={}; self.challenges={}; self.sessions={}; self.saved={}; self.hints=[]; self.history=[]; self.evidence_ids=set(); self.evidence_application_count=0
 def add_user(self,user_id,age_group):
  if user_id in self.users: raise ValueError('duplicate user')
  self.users[user_id]={'age_group':age_group,'completed':[]}; return self.users[user_id]
 def add_challenge(self,challenge_id,difficulty,kind):
  if difficulty not in {'beginner','intermediate','advanced'} or kind not in {'sort_numbers','sum_numbers'}: raise ValueError('invalid challenge')
  self.challenges[challenge_id]={'difficulty':difficulty,'kind':kind,'tests':[]}; return self.challenges[challenge_id]
 def start_session(self,session_id,user_ids,challenge_id):
  if challenge_id not in self.challenges or any(u not in self.users for u in user_ids): raise KeyError('unknown participant or challenge')
  self.sessions[session_id]={'users':list(user_ids),'challenge_id':challenge_id,'shared_code':'','revision':0,'messages':[]}; return self.sessions[session_id]
 def collaborate(self,session_id,user_id,code,message=''):
  s=self.sessions[session_id]
  if user_id not in s['users']: raise PermissionError('not in family session')
  if PRESERVE_COLLABORATION_STATE:
   s['shared_code']=code; s['revision']+=1; s['messages'].append({'user':user_id,'message':message}); self.history.append((session_id,user_id,s['revision']))
  return s['revision']
 def apply_test_evidence(self,evidence_id,challenge_id,cases):
  if APPLY_UNIQUE_TEST_EVIDENCE and evidence_id in self.evidence_ids: return {'status':'duplicate','applied':0}
  if challenge_id not in self.challenges: raise KeyError(challenge_id)
  normalized=[{'input':list(c['input']),'expected':list(c['expected'])} for c in cases]
  self.challenges[challenge_id]['tests']=normalized; self.evidence_ids.add(evidence_id); self.evidence_application_count+=1
  return {'status':'applied','applied':len(normalized)}
 def solve(self,challenge_id,values):
  kind=self.challenges[challenge_id]['kind']
  return sorted(list(values)) if kind=='sort_numbers' else sum(values)
 def run_registered_tests(self,challenge_id):
  rows=self.challenges[challenge_id]['tests']; passed=sum(self.solve(challenge_id,r['input'])==r['expected'] for r in rows)
  return {'passed':passed,'total':len(rows),'all_passed':passed==len(rows)}
 def submit(self,user_id,challenge_id,values):
  result=self.solve(challenge_id,values); report=self.run_registered_tests(challenge_id)
  if report['all_passed'] and challenge_id not in self.users[user_id]['completed']: self.users[user_id]['completed'].append(challenge_id)
  return {'result':result,'test_report':report}
 def get_hint(self,user_id,challenge_id,attempt):
  text='Compare adjacent values and preserve duplicates.' if self.challenges[challenge_id]['kind']=='sort_numbers' else 'Accumulate each value once.'
  if PRESERVE_COLLABORATION_STATE:self.hints.append({'user':user_id,'challenge':challenge_id,'attempt':attempt,'hint':text})
  return text
 def save_progress(self,user_id):
  snapshot={'completed':list(self.users[user_id]['completed']),'sessions':{k:v['revision'] for k,v in self.sessions.items() if user_id in v['users']}}
  if PRESERVE_COLLABORATION_STATE:self.saved[user_id]=snapshot
  return snapshot
 def load_progress(self,user_id): return dict(self.saved.get(user_id,{'completed':[],'sessions':{}}))
