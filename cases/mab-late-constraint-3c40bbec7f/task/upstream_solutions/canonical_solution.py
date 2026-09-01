DOMAIN='closed_loop_open_world_robot'
EVENT_SCHEMA='come_robot_recovery_safety_scope_v2'
USE_RETURNED_RESEARCH_AUTHORITY = True
PRESERVE_FIVE_QUESTION_STRUCTURE = True
TOPIC_QUESTION='How can a vision-language robot replan after perception, API, and grasp failures while satisfying explicit unsafe-action and human-intervention budgets in open environments?'
IMPORTANCE='Safety-bounded recovery would move open-ended robot planning from impressive demos toward auditable deployment in homes and workplaces.'
HARDNESS='Blurred observations, missed or wrong detections, invalid API sequences, grasp failures, and partial progress require different recovery actions while unsafe exploration must remain bounded.'
RESEARCH_GAP='Closed-loop robot systems report success and recovery but rarely measure whether recovery itself causes unsafe actions or excessive human intervention across failure types.'
METHOD='Extend a COME-robot-style active-perception and action-primitive loop with precondition checking, scene-graph rebuilding, execution monitors, and risk gates. Evaluate mobile manipulation tasks with injected missed detections, false detections, invalid calls, and grasp failures using SR, SSR, recovery rate, unsafe-action rate, intervention count, steps, and latency; ablate verification, replanning feedback, risk gates, and memory.'
SOURCE_PREMISES=['open-world robot navigation and manipulation', 'active perception', 'vision-language reasoning', 'action primitives', 'closed-loop replanning']
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
