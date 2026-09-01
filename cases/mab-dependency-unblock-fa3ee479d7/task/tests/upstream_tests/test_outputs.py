from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CONTRACT={'media_types':['image/jpeg','image/png','video/mp4'],'leader_only':['invite','assign_task'],'comment_votes':[-1,1]}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('craft_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_craft_output_schema_profiles_posts_and_artifacts():
 m=load_solution(); c=m.CollaborateCraft(); assert m.DOMAIN=='collaborate_craft'; c.apply_integrity_contract(CONTRACT); c.create_profile('ana','knitter','a.png'); c.post_project('p','ana','image/png','scarf.png','Blue scarf',['knitting']); assert c.search('knitting')['posts']==['p']; r,x=docs(); assert x['artifact_type']=='craft_group_integrity_closure' and x['event_receipt_sha256']==r['receipt_sha256']
def test_craft_media_leadership_membership_assignment_and_progress_behavior():
 m=load_solution(); c=m.CollaborateCraft(); c.apply_integrity_contract(CONTRACT); c.create_profile('lead','woodworker','l.png'); c.create_profile('member','painter','m.png'); c.create_group('g','lead','Community bench')
 for call in [lambda:c.post_project('bad','lead','application/exe','x','bad',['x']),lambda:c.invite('member','g','member')]:
  try:call()
  except (ValueError,PermissionError):pass
  else:raise AssertionError('integrity bypassed')
 c.invite('lead','g','member'); c.assign_task('lead','g','paint','member'); assert c.complete_task('member','g','paint')==1.0
def test_craft_comments_votes_messages_and_search_are_preserved():
 m=load_solution(); c=m.CollaborateCraft(); c.apply_integrity_contract(CONTRACT); c.create_profile('a','knitting fan','a.png'); c.create_profile('b','woodworking fan','b.png'); c.post_project('p','a','image/jpeg','x.jpg','Warm scarf',['knitting']); c.create_group('g','a','Scarf team'); c.invite('a','g','b'); cid=c.comment('b','p','Helpful pattern'); assert c.vote('a',cid,1)==1; c.message('a','b','hello'); c.message('b','g','ready',True); result=c.search('scarf'); assert result['posts']==['p'] and result['groups']==['g'] and len(c.messages)==2 and c.comments[cid]['score']==1
def test_craft_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='craft_group_integrity_v2' and set(r['authority']['media_types'])=={'image/jpeg','image/png','video/mp4'} and set(r['authority']['leader_only'])=={'invite','assign_task'}; assert c['upstream_depth']==4 and c['preserved_workflows']==['user_profiles','craft_posts_and_tags','comments_and_votes','private_and_group_messages']
