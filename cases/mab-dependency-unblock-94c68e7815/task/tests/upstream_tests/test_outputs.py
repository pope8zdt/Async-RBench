from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs():return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(k):
 r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-94c68e7815' and c['source_task_id']=='coding:020' and c['artifact_type']==k and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_quest_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='multi_agent_quest_creator'; assert hasattr(m,'QuestCreator'); assert_closure('versioned_quest_balance_closure')
def test_quest_structured_balance_enemy_strength_rewards_and_versioned_adjustments():
 m=load_solution(); app=m.QuestCreator(); app.create('q','a','combat',[{'strength':10},{'strength':8}],5,['win']); low=app.balance('q',10); assert set(low)=={'quest_version','difficulty_score','fairness_band','ranked_adjustments'} and low['fairness_band']=='under_rewarded'; stronger=m.QuestCreator(); stronger.create('q','a','combat',[{'strength':20},{'strength':18}],5,['win']); assert stronger.balance('q',10)['difficulty_score']>low['difficulty_score']; app.apply_adjustment('q',low,0,'a'); assert len(app.quests['q']['versions'])==2
def test_quest_history_revert_simulations_and_ratings_are_preserved():
 m=load_solution(); app=m.QuestCreator(); app.create('q','a','combat',[{'strength':10}],5,['win']); result=app.balance('q',5); app.apply_adjustment('q',result,0,'a'); assert app.revert('q',1)['version']==1; app.simulate('q',2); app.ratings.append(('q',5)); assert app.quests['q']['simulations'][0]['success'] is True and app.ratings==[('q',5)]
def test_quest_event_contract_and_closure():
 m=load_solution(); r,c=event_docs(); assert m.EVENT_SCHEMA=='quest_balance_v2'; assert r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['version_bound'] is True; assert c['preserved_workflows']==['quest_history','revert_points','simulation_results','community_ratings']
