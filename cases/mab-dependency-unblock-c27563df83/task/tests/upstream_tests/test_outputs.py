from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); POLICY={'money_unit':'integer_cents','roles':['owner','edit','view'],'spending_alert_percent':80}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('budget_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_budget_output_schema_shared_budget_and_closure():
 m=load_solution(); x=m.BudgetSync(); x.add_user('a',{'currency':'USD'}); x.apply_budget_policy(POLICY); x.create_budget('home','a','Home',['rent','food'],50000); r,c=docs(); assert m.DOMAIN=='budget_sync' and c['artifact_type']=='budget_sync_policy_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_budget_permissions_integer_money_dashboard_and_notifications():
 m=load_solution(); x=m.BudgetSync(); [x.add_user(u,{}) for u in ['a','b','c']]; x.apply_budget_policy(POLICY); x.create_budget('home','a','Home',['income','rent'],10000); x.invite('a','home','b','edit'); x.invite('a','home','c','view'); x.add_transaction('a','home','income','income',100000); x.add_transaction('b','home','expense','rent',80000)
 try:x.add_transaction('c','home','expense','rent',1)
 except PermissionError:pass
 else:raise AssertionError('view role wrote transaction')
 assert x.dashboard('c','home')['balance_cents']==20000 and any(n['kind']=='spending_limit_exceeded' for n in x.notifications)
def test_budget_visualization_suggestions_feedback_and_history_are_preserved():
 m=load_solution(); x=m.BudgetSync(); x.add_user('a',{}); x.apply_budget_policy(POLICY); x.create_budget('b','a','B',['income','rent','food'],0); x.add_transaction('a','b','income','income',100000); x.add_transaction('a','b','expense','rent',70000); x.add_transaction('a','b','expense','food',10000); x.set_chart('a','b','bar'); x.submit_feedback('a','add forecast'); assert x.suggestions('b')==['reduce:rent'] and x.dashboard('a','b')['chart']=='bar' and x.feedback[0]['text']=='add forecast'
def test_budget_complete_policy_event_and_final_reverification():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='shared_budget_policy_v2' and r['authority']['money_unit']=='integer_cents' and r['authority']['spending_alert_percent']==80; assert c['upstream_depth']==4 and c['preserved_workflows']==['user_profiles_and_permissions','shared_budget_transactions','notifications_and_goals','visualization_and_feedback']
