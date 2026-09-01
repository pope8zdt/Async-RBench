DOMAIN='sports_team_syncer'
EVENT_SCHEMA='sports_video_metric_calibration_v2'
USE_CALIBRATED_VIDEO_METRICS = True
PRESERVE_TEAM_WORKSPACE = True
class SportsTeamSyncer:
 def __init__(self): self.users={}; self.videos={}; self.metrics=[]; self.posts=[]; self.training=[]; self.contract=None
 def add_user(self,user_id,role):
  if role not in {'coach','player','analyst'}: raise ValueError('invalid role')
  self.users[user_id]=role
 def apply_calibration(self,contract):
  if contract.get('speed_unit')!='m/s' or contract.get('accuracy_range')!=[0,1] or contract.get('max_video_mb')!=500: raise ValueError('invalid calibration')
  self.contract=dict(contract); return self.contract
 def upload_video(self,user_id,video_id,size_mb,frames):
  if self.users.get(user_id) not in {'coach','analyst'} or size_mb<=0: raise PermissionError('upload denied')
  if USE_CALIBRATED_VIDEO_METRICS and (not self.contract or size_mb>self.contract['max_video_mb']): raise ValueError('video outside calibrated bounds')
  self.videos[video_id]={'owner':user_id,'size_mb':size_mb,'frames':list(frames)}; return self.videos[video_id]
 def analyze(self,user_id,video_id,player_id):
  if self.users.get(user_id) not in {'coach','analyst'}: raise PermissionError('analysis denied')
  frames=self.videos[video_id]['frames']
  if not frames: raise ValueError('empty video')
  speed=sum(f['distance_m']/f['seconds'] for f in frames)/len(frames); accuracy=sum(f['accurate'] for f in frames)/len(frames); agility=sum(f['direction_changes'] for f in frames)/len(frames)
  row={'video':video_id,'player':player_id,'speed_m_s':speed,'accuracy':accuracy,'agility':agility}; self.metrics.append(row); return row
 def dashboard(self,viewer,player_id=None):
  if viewer not in self.users: raise PermissionError('login required')
  rows=[m for m in self.metrics if player_id is None or m['player']==player_id]; return {'current':rows[-1] if rows else None,'history':rows}
 def post(self,user_id,text,attachment_type=None,attachment=None):
  if user_id not in self.users or not text or attachment_type not in {None,'image','video'}: raise ValueError('invalid post')
  row={'user':user_id,'text':text,'attachment_type':attachment_type,'attachment':attachment}
  if PRESERVE_TEAM_WORKSPACE:self.posts.append(row)
  return row
 def plan_training(self,coach,title,participants):
  if self.users.get(coach)!='coach' or not set(participants)<=set(self.users): raise PermissionError('coach planning required')
  row={'coach':coach,'title':title,'participants':list(participants)}
  if PRESERVE_TEAM_WORKSPACE:self.training.append(row)
  return row
