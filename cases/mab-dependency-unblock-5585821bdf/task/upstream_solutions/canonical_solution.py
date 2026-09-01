DOMAIN='driving_counterfactual_explanations'
EVENT_SCHEMA='driving_causal_explanation_protocol_v2'
USE_RETURNED_RESEARCH_AUTHORITY = True
PRESERVE_FIVE_QUESTION_STRUCTURE = True
TOPIC_QUESTION='Can causal concept and counterfactual explanations faithfully describe why an autonomous-driving model stops, turns, or overtakes in complex urban scenes?'
IMPORTANCE='Faithful local explanations can improve debugging, liability analysis, bias discovery, operator trust, and safe deployment of black-box driving systems.'
HARDNESS='Traffic actors, lights, lane markings, distance and lateral space are correlated; interventions must remain physically plausible, preserve scene semantics, and separate model causality from human expectation.'
RESEARCH_GAP='Saliency maps can behave like edge detectors and remain insensitive to the model, while prior concept explanations rarely combine causal fidelity, counterfactual validity, stability and human usefulness.'
METHOD='Learn scene concepts for traffic lights, pedestrians, lane markings, front-vehicle distance and lateral clearance, then generate physically plausible counterfactual interventions for BDD100K and nuScenes driving decisions. Measure deletion/intervention fidelity, counterfactual validity, stability, sparsity, simulator safety and expert/user agreement; compare saliency and concept baselines and ablate concept supervision, causal graph and plausibility constraints. Expected results yield more faithful and understandable failure explanations.'
SOURCE_PREMISES=['safety-critical autonomous driving', 'black-box local explanations', 'saliency maps can be misleading', 'human trust and liability']
class ResearchProposal:
 def __init__(self): self.authority=None; self.premises=list(SOURCE_PREMISES)
 def apply_authority(self,authority):
  if authority.get('contract')!=EVENT_SCHEMA: raise ValueError('wrong research authority')
  self.authority=dict(authority); return self.authority
 def build_5q(self):
  if USE_RETURNED_RESEARCH_AUTHORITY and not self.authority: raise RuntimeError('research authority required')
  method=METHOD if USE_RETURNED_RESEARCH_AUTHORITY else 'Run a generic baseline without the returned benchmark contract.'
  rows={'question_1':TOPIC_QUESTION,'question_2':IMPORTANCE,'question_3':HARDNESS,'question_4':RESEARCH_GAP,'question_5':method}
  return rows if PRESERVE_FIVE_QUESTION_STRUCTURE else {'question_1':rows['question_1'],'question_5':rows['question_5']}
 def render(self):
  q=self.build_5q(); return '\n\n'.join(f'**[Question {i}] - {q[f"question_{i}"]}' for i in range(1,6))
