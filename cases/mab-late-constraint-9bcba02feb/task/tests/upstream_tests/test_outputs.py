from __future__ import annotations
import json,pathlib
O=pathlib.Path('/app/output_data');F=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json');SOURCE='bargaining:009';CASE='mab-late-constraint-9bcba02feb';CURRENT=2;PRICE=21.2;FLOOR=21.1905;CEILING=22.0;TERMS={"two_piece_holiday_set": "verified", "quality_rating_evidence": 4.6, "warranty_months": 12, "after_sales_support": True, "battery_condition": "not_applicable_verified", "production_schedule": "volume-aligned"};STALE={"revision": 1, "price": 24.93, "warranty_months": 0, "quality_evidence": "missing", "status": "superseded"};PRESERVED=["seller profit-margin floor", "seller production-demand balance", "buyer warranty and after-sales priority", "source-stated battery condition explicitly dispositioned"];EVIDENCE='6cbfa25aae32267135484905bbc784206a3e710839e343e34c4dc809e513cd03'
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
