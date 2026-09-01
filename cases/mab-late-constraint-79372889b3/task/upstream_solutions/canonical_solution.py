DOMAIN='open_lookup_free_visual_tokenizer'
EVENT_SCHEMA='open_magvit_efficiency_benchmark_v2'
USE_RETURNED_RESEARCH_AUTHORITY = True
PRESERVE_FIVE_QUESTION_STRUCTURE = True
TOPIC_QUESTION='How can an open lookup-free visual tokenizer and asymmetric sub-token autoregressive model scale codebook capacity while improving reconstruction, generation quality, utilization, throughput, and memory?'
IMPORTANCE='An open, efficient tokenizer would remove a closed-source bottleneck and enable reproducible scalable autoregressive image generation.'
HARDNESS='Super-large binary codebooks create optimization, utilization and vocabulary-prediction challenges; factorization choices trade reconstruction detail against sequence length, throughput and memory.'
RESEARCH_GAP='Existing VQ tokenizers underuse limited codebooks, while the strongest lookup-free tokenizer is closed and prior replications do not jointly study factorization, generation scaling and efficiency.'
METHOD='Reimplement lookup-free quantization and asymmetric token factorization with next-sub-token prediction on ImageNet 128 and 256, scale plain autoregressive transformers, and report rFID, generation FID, codebook utilization, entropy, throughput, peak memory and scaling curves. Compare VQ-VAE, lookup-free and masked-generation baselines; ablate codebook bits, sub-vocabulary split, interaction loss and model size. Expected results retain Open-MAGVIT-level reconstruction while improving open AR quality-efficiency trade-offs.'
SOURCE_PREMISES=['lookup-free visual quantization', 'closed MAGVIT-v2 tokenizer', 'asymmetric token factorization', 'next sub-token prediction', 'autoregressive image generation']
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
