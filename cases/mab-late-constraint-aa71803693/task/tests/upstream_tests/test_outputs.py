from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
TIERS=[{'name':'single_event','unit_price':27.5,'minimum_quantity':1,'contract_months':0,'shipping_days':6},{'name':'planner_partner','unit_price':25.5,'minimum_quantity':12,'contract_months':12,'shipping_days':4}]
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('elephant_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_elephant_output_schema_product_and_summary():
 m=load_solution(); n=m.BabyShowerNegotiation(); assert m.DOMAIN=='elephant_baby_shower_bargaining' and n.product=='Jungle Baby Shower Theme Centerpiece' and n.original_price==29.99 and n.rating==4.7; assert all(h in n.render_summary() for h in ['Iteration Summary','Agent Actions and Tools Used','Key Strategies and Observations','Progress Towards Agreement']); r,c=docs(); assert c['artifact_type']=='elephant_centerpiece_supply_agreement_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_elephant_latest_supply_terms_replace_price_only_draft():
 m=load_solution(); n=m.BabyShowerNegotiation(); n.buyer_draft(24,12,1); n.apply_supply_terms(TIERS,3); selected=n.select_tier('buyer','planner_partner',12,4); stale=n.select_tier('buyer','single_event',1,2); assert selected['unit_price']==25.5 and selected['contract_months']==12 and stale['status']=='stale' and n.current_offer['name']=='planner_partner'; agreement=n.finalize(); assert agreement['quantity']==12 and agreement['shipping_days']==4 and agreement['rating']==4.7
def test_elephant_priorities_rejections_and_ledger_are_preserved():
 m=load_solution(); n=m.BabyShowerNegotiation(); n.buyer_draft(24,1,1); n.apply_supply_terms(TIERS,3); assert n.select_tier('buyer','planner_partner',2,4)['status']=='rejected'; n.select_tier('buyer','single_event',1,5); n.finalize(); assert n.rejected[0]['reason']=='below_minimum_quantity' and n.buyer_priorities==['price','quality'] and n.seller_goal=='long_term_contract' and len(n.transcript)>=4
def test_elephant_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='elephant_centerpiece_supply_v2' and r['authority']['product']=='Jungle Baby Shower Theme Centerpiece' and r['authority']['rating']==4.7 and len(r['authority']['tiers'])==2; assert c['upstream_depth']==4 and c['preserved_workflows']==['negotiation_transcript','rejected_offers','buyer_quality_priority','seller_long_term_goal']
