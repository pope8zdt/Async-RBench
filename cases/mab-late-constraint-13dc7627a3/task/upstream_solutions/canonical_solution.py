DOMAIN='streaming_sequence_architectures'
EVENT_SCHEMA='streaming_sequence_budget_v2'
USE_RETURNED_RESEARCH_AUTHORITY = True
PRESERVE_FIVE_QUESTION_STRUCTURE = True
TOPIC_QUESTION='When do temporal convolutional networks outperform LSTM and GRU models under streaming latency, peak-memory, and long-history constraints across sequence tasks?'
IMPORTANCE='A controlled answer would replace architecture folklore with deployable accuracy-efficiency guidance for audio, language and long-memory systems.'
HARDNESS='Receptive field, recurrent state, truncation, batching and hardware kernels couple accuracy, latency and memory, so offline parameter-matched comparisons do not predict streaming behavior.'
RESEARCH_GAP='Prior broad TCN comparisons emphasize accuracy and effective memory but do not jointly control online latency, peak memory, chunk size and history under one protocol.'
METHOD='Compare residual dilated TCN, LSTM and GRU models on polyphonic music, word/character language modeling and synthetic copy/addition stress tests using matched parameters and streaming chunks. Report likelihood or accuracy, p50/p95 latency, peak memory, throughput and effective-history probes; ablate dilation, kernel, recurrent state, truncation and chunk size. Expected results map where TCN parallelism or recurrent state gives the best constrained frontier.'
SOURCE_PREMISES=['TCN versus recurrent sequence modeling', 'polyphonic music and language tasks', 'synthetic long-memory stress tests', 'effective receptive field']
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
