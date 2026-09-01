DOMAIN='text_to_image_f_divergence_alignment'
EVENT_SCHEMA='f_divergence_alignment_derivation_v3'
USE_DERIVED_F_DIVERGENCE_AUTHORITY = True
PRESERVE_FIVE_QUESTION_STRUCTURE = True
class DivergenceAlignmentProposal:
 def __init__(self):
  self.premises=['human preference alignment','separate reward-model complexity','reverse-KL mode seeking can reduce diversity','implicit-reward optimization']; self.authority=None
 def apply_derivation(self,authority):
  required={'divergences','assumptions','consistency_case'}
  if not required<=set(authority): raise ValueError('incomplete derivation')
  self.authority=dict(authority); return self.authority
 def build_5q(self):
  if USE_DERIVED_F_DIVERGENCE_AUTHORITY and not self.authority: raise RuntimeError('mathematical authority required')
  method=('Optimize text-to-image preferences with direct pairwise implicit rewards under reverse KL, forward KL, Jensen-Shannon, and alpha-divergence constraints; require absolute continuity, a convex generator, and finite preference log-ratios; verify that reverse KL recovers Diffusion-DPO. Use Pick-a-Pic and HPS preference pairs, compare Diffusion-DPO and reward-model RLHF baselines, report PickScore, ImageReward, CLIP alignment, LPIPS diversity, prompt-level coverage, stability, and memory, and ablate divergence, coefficient, and data scale. Expected results are comparable preference alignment with measurably better diversity and stable optimization.') if USE_DERIVED_F_DIVERGENCE_AUTHORITY else 'Use a generic preference objective and report image quality.'
  rows={
   'question_1':'Which f-divergence constraints best align text-to-image generators with human preferences without collapsing output diversity?',
   'question_2':'Solving this would connect direct preference alignment to controllable quality-diversity trade-offs and reduce reliance on a separately trained reward model.',
   'question_3':'The objective must estimate preference log-ratios stably while satisfying absolute-continuity and convex-generator assumptions; naive repeated fine-tuning can overfit pairs and collapse modes.',
   'question_4':'Prior text-to-image alignment emphasizes reverse KL and underexplores forward KL, Jensen-Shannon, and alpha-divergence in one controlled direct-preference framework with diversity evaluation.',
   'question_5':method,
  }
  return rows if PRESERVE_FIVE_QUESTION_STRUCTURE else {'question_1':rows['question_1'],'question_5':rows['question_5']}
 def render(self):
  q=self.build_5q(); return '\n\n'.join(f'**[Question {i}]**\n{q[f"question_{i}"]}' for i in range(1,6))
