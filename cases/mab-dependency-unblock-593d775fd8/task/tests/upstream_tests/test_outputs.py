from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
    p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
    r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-593d775fd8' and c['source_task_id']=='coding:011'; assert c['artifact_type']==kind and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True

def test_boardgame_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='board_game_team_collaborator'; assert hasattr(m,'BoardGameTeamCollaborator'); assert_closure('ranked_boardgame_strategy_closure')

def test_boardgame_ranked_recommendations_follow_trend_and_permitted_roles():
    m=load_solution(); app=m.BoardGameTeamCollaborator(); app.add_game('quest',['scout','builder'],{'win':10}); app.create_team('t',{'ana':'scout','bo':'builder'}); rec=app.recommend('quest','t',-3,{'ana':9,'bo':2}); assert rec['recommendations'][0]['player']=='bo'; assert rec['recommendations'][0]['rank']==1; assert rec['recommendations'][0]['expected_score_delta']>rec['recommendations'][1]['expected_score_delta']
    try: app.apply_role_adjustment('quest','t','ana','wizard')
    except ValueError: pass
    else: raise AssertionError('invalid role accepted')

def test_boardgame_advice_preserves_leaderboard_rules_turns_and_membership():
    m=load_solution(); app=m.BoardGameTeamCollaborator(); app.add_game('quest',['scout'],{'win':10}); app.create_team('t',{'ana':'scout'}); app.record_score('t',7); app.turn_order=['t']; before=(app.leaderboard(),dict(app.games['quest']['scoring']),dict(app.teams['t']),list(app.turn_order)); rec=app.recommend('quest','t',-1,{'ana':5}); after=(app.leaderboard(),dict(app.games['quest']['scoring']),dict(app.teams['t']),list(app.turn_order)); assert before==after; assert rec['leaderboard_unchanged'] is True

def test_boardgame_event_contract_and_closure():
    m=load_solution(); receipt,closure=event_docs(); assert m.EVENT_SCHEMA=='ranked_strategy_v2'; assert receipt['authority']['advisory_only'] is True; assert receipt['authority']['contract']==m.EVENT_SCHEMA; assert closure['preserved_workflows']==['leaderboard_totals','game_rules','turn_order','team_membership']
