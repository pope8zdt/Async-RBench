from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def tiers(): return [{'name':'defect','price':45.0,'warranty_days':90,'replacement':'defect_only','support':'standard'},{'name':'annual','price':48.0,'warranty_days':365,'replacement':'one_year_replacement','support':'dedicated'}]
def assert_closure(kind):
 r,c=docs(); assert c['artifact_type']==kind and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_air_filter_output_schema_summary_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='merv13_air_filter_bargaining' and hasattr(m,'AirFilterNegotiation'); n=m.AirFilterNegotiation(); text=n.render_summary(); assert all(h in text for h in ['Iteration Summary','Agent Actions and Tools Used','Key Strategies and Observations','Progress Towards Agreement']); assert_closure('air_filter_warranty_agreement_closure')
def test_air_filter_late_authority_supersedes_stale_offer_and_finalizes_explicit_terms():
 m=load_solution(); n=m.AirFilterNegotiation(); n.buyer_draft(43,365,'full_replacement','dedicated',1); n.apply_seller_tiers(tiers(),3); selected=n.select_tier('buyer','annual',4); assert selected['price']==48 and selected['warranty_days']==365; stale=n.buyer_draft(42,730,'full','premium',2) if not m.ENFORCE_LATEST_AUTHORITY else n.select_tier('buyer','defect',2); assert stale.get('status')=='stale'; assert n.current_offer['price']==48; assert n.finalize()=={'price':48.0,'warranty_days':365,'replacement':'one_year_replacement','support':'dedicated'}
def test_air_filter_margin_rejections_transcript_and_priorities_are_preserved():
 m=load_solution(); n=m.AirFilterNegotiation(); n.buyer_draft(43,365,'full','dedicated',1); n.apply_seller_tiers(tiers(),3); assert n.counter('buyer',40,365,'full','dedicated',4)['status']=='rejected'; n.select_tier('buyer','defect',5); n.finalize(); assert n.rejected[0]['reason']=='below_margin_floor'; assert n.transcript and n.buyer_priorities==['warranty','after_sales_support','timely_delivery'] and n.seller_margin_floor==43.34
def test_air_filter_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='merv13_warranty_tiers_v2'; assert r['authority']['contract']==m.EVENT_SCHEMA and len(r['authority']['tiers'])==2 and r['authority']['seller_margin_floor']==43.34; assert c['preserved_workflows']==['negotiation_transcript','rejected_offers','buyer_priorities','seller_margin_floor']
