from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CAL={'speed_unit':'m/s','accuracy_range':[0,1],'max_video_mb':500,'large_file_policy':'reject'}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('sports_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_sports_output_schema_roles_dashboard_and_closure():
 m=load_solution(); s=m.SportsTeamSyncer(); s.add_user('c','coach'); s.apply_calibration(CAL); r,c=docs(); assert m.DOMAIN=='sports_team_syncer' and s.dashboard('c')=={'current':None,'history':[]} and c['artifact_type']=='sports_video_calibration_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_sports_video_access_calibrated_metrics_and_large_file_behavior():
 m=load_solution(); s=m.SportsTeamSyncer(); [s.add_user(*x) for x in [('c','coach'),('p','player'),('a','analyst')]]; s.apply_calibration(CAL); frames=[{'distance_m':10,'seconds':2,'accurate':1,'direction_changes':3},{'distance_m':6,'seconds':2,'accurate':0,'direction_changes':1}]; s.upload_video('a','v',100,frames); metric=s.analyze('c','v','p'); assert metric=={'video':'v','player':'p','speed_m_s':4.0,'accuracy':0.5,'agility':2.0}
 try:s.upload_video('p','bad',1,frames)
 except PermissionError:pass
 else:raise AssertionError('player uploaded analysis video')
 try:s.upload_video('c','huge',501,frames)
 except ValueError:pass
 else:raise AssertionError('oversized video accepted')
def test_sports_workspace_media_training_and_metric_history_are_preserved():
 m=load_solution(); s=m.SportsTeamSyncer(); [s.add_user(*x) for x in [('c','coach'),('p','player'),('a','analyst')]]; s.apply_calibration(CAL); s.upload_video('c','v',10,[{'distance_m':4,'seconds':1,'accurate':1,'direction_changes':2}]); s.analyze('a','v','p'); s.post('p','review sprint','video','clip.mp4'); s.plan_training('c','agility',['p']); assert s.posts[0]['attachment']=='clip.mp4' and s.training[0]['participants']==['p'] and len(s.dashboard('p','p')['history'])==1
def test_sports_calibration_event_and_final_reverification():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='sports_video_metric_calibration_v2' and r['authority']['speed_unit']=='m/s' and r['authority']['max_video_mb']==500; assert c['upstream_depth']==4 and c['source_semantics_reverified'] is True
