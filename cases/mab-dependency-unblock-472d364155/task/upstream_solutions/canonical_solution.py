DOMAIN='monocular_expressive_avatar'
EVENT_SCHEMA='exavatar_coverage_benchmark_v2'
USE_RETURNED_RESEARCH_AUTHORITY = True
PRESERVE_FIVE_QUESTION_STRUCTURE = True
TOPIC_QUESTION='How can a short monocular video produce an expressive whole-body avatar that generalizes to unseen facial expressions, hand poses, body poses, and occluded geometry?'
IMPORTANCE='This would democratize animatable avatars for telepresence, entertainment, and interaction without calibrated multi-view or RGBD capture.'
HARDNESS='A monocular clip has sparse expression and pose coverage, self-occlusion, non-rigid clothing, and ambiguous unseen surfaces, so naive fitting bakes appearance and fails under novel articulation.'
RESEARCH_GAP='Existing casual-video avatars emphasize body motion or require scans and accurate registrations; they do not jointly quantify face, hand, body, and occlusion generalization.'
METHOD='Train an uncertainty-aware SMPL-X-conditioned 3D Gaussian surface model from monocular video, augment expression and hand/body pose coverage, and regularize occluded geometry. Evaluate on held-out people and novel motions with face/hand/body pose strata, rendering PSNR, SSIM and LPIPS, geometry error, identity consistency and runtime; ablate uncertainty, pose augmentation, mesh connectivity, and Gaussian attachment. Expected results improve novel-expression and occlusion rendering without sacrificing real-time animation.'
SOURCE_PREMISES=['short monocular video', 'SMPL-X whole-body control', '3D Gaussian splatting', 'limited expression and pose diversity', 'occluded geometry ambiguity']
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
