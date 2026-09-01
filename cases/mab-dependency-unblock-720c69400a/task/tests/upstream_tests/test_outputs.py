from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
    p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
    r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-720c69400a' and c['source_task_id']=='coding:004'; assert c['artifact_type']==kind and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True

def test_price_tracker_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='price_tracker_collaborator'; assert hasattr(m,'PriceTrackerCollaborator'); assert_closure('normalized_price_alert_closure')

def test_price_tracker_converts_quotes_filters_stale_unavailable_and_alerts():
    m=load_solution(); app=m.PriceTrackerCollaborator(); app.register('a@x.com','pass'); app.watch('a@x.com','p','https://shop/p',100,'USD'); quotes=[{'retailer':'one','product_id':'p','price':95,'currency':'USD','available':True,'observed_at':1000},{'retailer':'two','product_id':'p','price':90,'currency':'EUR','available':True,'observed_at':1000},{'retailer':'old','product_id':'p','price':1,'currency':'USD','available':True,'observed_at':0},{'retailer':'down','product_id':'p','price':0,'currency':'USD','available':False,'observed_at':1000}]; best=app.ingest_quotes('p',quotes,1100); assert best['retailer']=='one'; assert app.notifications==[('a@x.com','threshold_met','p','one')]

def test_price_tracker_preserves_thresholds_groups_sharing_and_preferences():
    m=load_solution(); app=m.PriceTrackerCollaborator(); app.register('a@x.com','pass'); app.register('b@x.com','pass'); app.create_group('g','a@x.com'); app.join_group('g','b@x.com'); app.watch('a@x.com','p','https://shop/p',50); sent=app.share_alert('g','a@x.com','p'); assert sent==['b@x.com']; assert app.watchlists['a@x.com']['p']['threshold']==50; assert app.users['b@x.com']['preferences']['in_app'] is True

def test_price_tracker_event_contract_and_closure():
    m=load_solution(); receipt,closure=event_docs(); assert m.EVENT_SCHEMA=='normalized_quote_v2'; assert receipt['authority']['selection']=='fresh_available_converted_minimum'; assert receipt['authority']['contract']==m.EVENT_SCHEMA; assert closure['event_receipt_sha256']==receipt['receipt_sha256']
