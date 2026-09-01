from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CONTRACT={'order':['profiles','virtual_tours','language_exchange','workshops','feedback'],'translation_required':True,'rating_requires_experience':True}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('culture_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_culture_output_schema_profiles_tours_and_artifacts():
 m=load_solution(); h=m.CulturalExchangeHub(); assert m.DOMAIN=='cultural_exchange_hub'; h.apply_dependency_contract(CONTRACT); h.register('ana','Peru',['music'],'ana.png'); h.add_tour('machu','Machu Picchu',{'gate':'History'},'audio-es'); assert h.visit_tour('ana','machu','gate')=={'info':'History','audio':'audio-es'}; r,c=docs(); assert c['artifact_type']=='cultural_exchange_dependency_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_culture_dependency_order_translation_workshop_and_rating_behavior():
 m=load_solution(); h=m.CulturalExchangeHub(); h.apply_dependency_contract(CONTRACT); h.register('a','Peru',['food'],'a.png'); h.register('b','Japan',['language'],'b.png'); h.add_tour('t','Temple',{'h':'Heritage'},'guide'); h.add_workshop('w','expert','live')
 for call in [lambda:h.language_exchange('a','b','ja','hello'),lambda:h.join_workshop('a','w'),lambda:h.rate('a','w',5,'great')]:
  try:call()
  except (RuntimeError,PermissionError):pass
  else:raise AssertionError('dependency bypassed')
 h.visit_tour('a','t','h'); session=h.language_exchange('a','b','ja','hello'); h.join_workshop('a','w','How is it made?'); assert session['translation']=='[ja] hello' and h.rate('a','w',5,'great')['score']==5
def test_culture_profiles_learning_activity_and_discussions_are_preserved():
 m=load_solution(); h=m.CulturalExchangeHub(); h.apply_dependency_contract(CONTRACT); h.register('a','Ghana',['art'],'a.png'); h.register('b','Italy',['art'],'b.png'); h.add_tour('t','Gallery',{'x':'Artifact'},'audio'); h.visit_tour('a','t','x'); h.language_exchange('a','b','it','ciao'); h.add_workshop('w','curator','recorded'); h.join_workshop('a','w','Materials?'); assert h.profiles['a']['background']=='Ghana' and h.tour_visits and h.language_sessions and h.discussions==[('w','a','Materials?')]
def test_culture_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='cultural_exchange_dependency_v2' and r['authority']['order']==['profiles','virtual_tours','language_exchange','workshops','feedback'] and r['authority']['translation_required'] is True; assert c['upstream_depth']==4 and c['preserved_workflows']==['user_profiles','tour_progress','language_sessions','workshop_discussions']
