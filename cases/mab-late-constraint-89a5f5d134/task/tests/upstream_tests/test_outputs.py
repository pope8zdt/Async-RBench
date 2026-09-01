from __future__ import annotations
import json,pathlib
O=pathlib.Path('/app/output_data');F=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json');SOURCE='bargaining:015';CASE='mab-late-constraint-89a5f5d134';CURRENT=2;PRICE=10.8;FLOOR=10.791;CEILING=11.0;TERMS={"compatibility": "Xbox One verified", "conductive_film_inspection": "passed", "rating_evidence": 4.4, "bundled_logistics": True, "battery_condition": "not_applicable_verified"};STALE={"revision": 1, "price": 11.99, "compatibility": "unverified", "bundled_logistics": False, "status": "superseded"};PRESERVED=["seller production-demand balance", "seller logistics-cost reduction", "buyer scalability and premium-feature priority", "source-stated battery condition explicitly dispositioned"];EVIDENCE='aa80cc353bca6a8aeba33935ab585e7da8eb2c0da1e349f643626fd212eb092c'
def a():return json.loads((O/'agreement.json').read_text())
def l():return json.loads((O/'negotiation_ledger.json').read_text())
def test_native_binding():
 n=json.loads(F.read_text());assert n['case_id']==CASE and n['source_task_id']==SOURCE and n['native_evaluator_method'].endswith('Evaluator.evaluate_task_world') and n['agreement_reached'] and n['passed'];assert min(v for x in n['native_evaluator_metrics'].values() for v in x.values())>=4
def test_current_revision():assert a()['accepted_revision']==CURRENT==l()['accepted_revision'] and l()['current_offer']['price_usd']==PRICE
def test_price_bounds():
 x=a();assert x['seller_floor_usd']==FLOOR and x['buyer_ceiling_usd']==CEILING and FLOOR<=x['price_usd']<=CEILING
def test_product_terms():assert a()['terms']==TERMS and a()['agreement_reached']
def test_stale_excluded():assert l()['superseded_revisions']==[STALE] and STALE['revision']<l()['accepted_revision'] and l()['current_offer']['price_usd']!=STALE['price']
def test_schema_and_preservation():
 x=a();assert set(x)=={'source_task_id','product','accepted_revision','price_usd','seller_floor_usd','buyer_ceiling_usd','terms','agreement_reached','preserved_priorities','native_evidence_sha256'} and x['native_evidence_sha256']==EVIDENCE and x['preserved_priorities']==PRESERVED and l()['chronology_verified']
