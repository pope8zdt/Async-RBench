from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); RULES={'common_threat':'alliance_required','score_weights':{'territory':10,'technology':7,'economy':1},'difficulty_bounds':[1,5]}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('galactic_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_galactic_output_schema_agents_and_closure():
 m=load_solution(); g=m.GalacticDominion(); g.add_agent('a','science'); g.apply_event_rulebook(RULES); r,c=docs(); assert m.DOMAIN=='galactic_dominion' and g.agents['a']['territory']==1 and c['artifact_type']=='galactic_dominion_rulebook_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_galactic_turn_resources_research_scoring_and_difficulty():
 m=load_solution(); g=m.GalacticDominion(); g.add_agent('a','science'); g.add_agent('b','fleet'); g.apply_event_rulebook(RULES); g.build('a','lab',20); g.research('a','warp',10); g.end_turn(); g.commission_fleet('b',30); assert g.score('a')==10+7+110 and 1<=g.adaptive_difficulty('a')<=5
def test_galactic_alliance_communication_and_common_threat_are_preserved():
 m=load_solution(); g=m.GalacticDominion(); g.add_agent('a','science'); g.add_agent('b','fleet'); g.apply_event_rulebook(RULES)
 try:g.resolve_dynamic_event('e','alien_invasion',['a','b'])
 except RuntimeError:pass
 else:raise AssertionError('unallied common threat accepted')
 g.negotiate_alliance('a','b','share sensors'); row=g.resolve_dynamic_event('e','alien_invasion',['a','b']); assert row['resolved'] and g.communications==[{'agents':('a','b'),'terms':'share sensors'}] and g.events[0]['event_id']=='e'
def test_galactic_event_rulebook_and_final_reverification():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='galactic_common_threat_rulebook_v2' and r['authority']['common_threat']=='alliance_required' and r['authority']['score_weights']=={'territory':10,'technology':7,'economy':1}; assert c['upstream_depth']==4 and c['source_semantics_reverified'] is True
