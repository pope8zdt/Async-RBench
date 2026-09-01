DOMAIN='language_collaborator'
EVENT_SCHEMA='language_edge_evidence_v2'
DEDUPLICATE_EDGE_EVIDENCE = True
PRESERVE_LEARNING_HISTORY = True
class LanguageCollaborator:
 def __init__(self): self.users={}; self.exercises={}; self.submissions={}; self.reviews=[]; self.seen_evidence=set(); self.contract=None
 def add_user(self,user_id):
  if not user_id or user_id in self.users: raise ValueError('unique user required')
  self.users[user_id]={'active':True}
 def apply_edge_evidence(self,evidence):
  evidence_id=evidence.get('evidence_id')
  if not evidence_id or evidence.get('suite')!='language_collaboration_edges': raise ValueError('invalid evidence')
  if DEDUPLICATE_EDGE_EVIDENCE and evidence_id in self.seen_evidence:return False
  self.seen_evidence.add(evidence_id); self.contract=dict(evidence); return True
 def create_exercise(self,exercise_id,owner,kind,prompt,answer=None,shared=True):
  if owner not in self.users or kind not in {'grammar','vocabulary','writing'} or not prompt: raise ValueError('invalid exercise')
  self.exercises[exercise_id]={'owner':owner,'kind':kind,'prompt':prompt,'answer':answer,'shared':bool(shared)}; return self.exercises[exercise_id]
 def submit(self,submission_id,user_id,exercise_id,response):
  ex=self.exercises[exercise_id]
  if user_id not in self.users or (not ex['shared'] and user_id!=ex['owner']) or not response: raise PermissionError('exercise unavailable')
  if ex['kind'] in {'grammar','vocabulary'}: feedback={'correct':response.strip().lower()==str(ex['answer']).strip().lower()}
  else:
   feedback={'suggestions':([x for x in ['capitalization','terminal punctuation'] if (x=='capitalization' and not response[:1].isupper()) or (x=='terminal punctuation' and response[-1:] not in '.!?')])}
  row={'id':submission_id,'user':user_id,'exercise':exercise_id,'response':response,'feedback':feedback}; self.submissions[submission_id]=row; return row
 def peer_review(self,reviewer,submission_id,rating,comment):
  sub=self.submissions[submission_id]; ex=self.exercises[sub['exercise']]
  if reviewer not in self.users or reviewer in {sub['user'],ex['owner']} or not 1<=rating<=5 or not comment: raise PermissionError('independent peer review required')
  row={'reviewer':reviewer,'submission':submission_id,'rating':rating,'comment':comment}
  if PRESERVE_LEARNING_HISTORY:self.reviews.append(row)
  return row
 def exercise_feedback(self,submission_id): return self.submissions[submission_id]['feedback']
