from __future__ import annotations
import json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='bargaining:001'; CASE_ID='mab-late-constraint-0e3747a21b'; CURRENT=2; PRICE=15.0; FLOOR=14.433; CEILING=17.0; TERMS={"compatibility": "HISENSE EQK confirmed", "warranty_months": 12, "delivery_days": 7, "after_sales_support": True}; STALE={"revision": 1, "price": 16.98, "warranty_months": 0, "delivery_days": 14, "status": "superseded"}; PRESERVED=["seller 15 percent discount floor", "buyer robust warranty and after-sales priority", "buyer timely-delivery priority"]; EVIDENCE='26b44adedfea18e204d5d242dc9fbccae1a256621772adc40456eddc444460c7'
def agreement(): return json.loads((OUT/'agreement.json').read_text())
def ledger(): return json.loads((OUT/'negotiation_ledger.json').read_text())
def test_native_world_evaluator_binding():
    n=json.loads(FIX.read_text()); assert n['case_id']==CASE_ID and n['source_task_id']==SOURCE_ID and n['native_evaluator_method'].endswith('Evaluator.evaluate_task_world') and n['agreement_reached'] and n['passed']; assert min(v for side in n['native_evaluator_metrics'].values() for v in side.values())>=4
def test_current_revision_is_accepted():
    a=agreement(); l=ledger(); assert a['accepted_revision']==CURRENT==l['accepted_revision'] and l['current_offer']['price_usd']==PRICE
def test_price_respects_case_specific_bounds():
    a=agreement(); assert a['seller_floor_usd']==FLOOR and a['buyer_ceiling_usd']==CEILING and FLOOR<=a['price_usd']<=CEILING
def test_product_specific_terms():
    a=agreement(); assert a['terms']==TERMS and a['agreement_reached']
def test_stale_offer_is_excluded():
    l=ledger(); assert l['superseded_revisions']==[STALE] and STALE['revision']<l['accepted_revision'] and l['current_offer']['price_usd']!=STALE['price']
def test_schema_evidence_and_preservation():
    a=agreement(); l=ledger(); assert set(a)=={'source_task_id','product','accepted_revision','price_usd','seller_floor_usd','buyer_ceiling_usd','terms','agreement_reached','preserved_priorities','native_evidence_sha256'}; assert a['native_evidence_sha256']==EVIDENCE and a['preserved_priorities']==PRESERVED and l['chronology_verified']
