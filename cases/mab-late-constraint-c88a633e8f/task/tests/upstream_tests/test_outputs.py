from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); TIERS=[{'name':'standard','price':149.0,'warranty_days':90,'support':'email','return_days':30,'shipping_days':7},{'name':'care_plus','price':159.0,'warranty_days':365,'support':'priority','return_days':60,'shipping_days':3}]
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('bag_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_rhapsody_output_schema_product_and_summary():
 m=load_solution(); n=m.RhapsodyBagNegotiation(); assert m.DOMAIN=='rhapsody_bag_bargaining' and n.product=='Rhapsody Cross Body Bag in Black, One Size' and n.original_price==149 and n.rating==4.5; assert all(h in n.render_summary() for h in ['Iteration Summary','Agent Actions and Tools Used','Key Strategies and Observations','Progress Towards Agreement']); r,c=docs(); assert c['artifact_type']=='rhapsody_bag_warranty_agreement_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_rhapsody_latest_matrix_supersedes_stale_price_only_offer():
 m=load_solution(); n=m.RhapsodyBagNegotiation(); n.provisional_offer(140,1); n.apply_matrix(TIERS,3); selected=n.select_tier('buyer','care_plus',4); stale=n.select_tier('buyer','standard',2); assert selected['warranty_days']==365 and selected['support']=='priority' and selected['shipping_days']==3 and stale['status']=='stale' and n.current_offer['name']=='care_plus'; assert n.finalize()['return_days']==60
def test_rhapsody_warranty_priorities_logistics_goal_and_ledger_are_preserved():
 m=load_solution(); n=m.RhapsodyBagNegotiation(); n.provisional_offer(145,1); n.apply_matrix(TIERS,3); n.select_tier('buyer','standard',4); n.finalize(); assert n.buyer_priorities==['comprehensive_warranty','after_sales_support'] and n.seller_goal=='reduce_logistics_cost' and len(n.transcript)==4; assert n.rejected==[]
def test_rhapsody_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='rhapsody_warranty_logistics_v2' and r['authority']['product']=='Rhapsody Cross Body Bag in Black, One Size' and len(r['authority']['tiers'])==2; assert c['upstream_depth']==4 and c['preserved_workflows']==['negotiation_transcript','rejected_offers','buyer_warranty_priority','seller_logistics_goal']
