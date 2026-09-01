from __future__ import annotations
import json,pathlib
O=pathlib.Path('/app/output_data');F=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json');SOURCE='bargaining:007';CASE='mab-late-constraint-c7d591d986';CURRENT=2;PRICE=93.0;FLOOR=87.9835;CEILING=93.0;TERMS={"charlie_boot_quality_inspection": "passed", "rating_evidence": 4.0, "long_term_contract_months": 12, "production_schedule": "demand-aligned", "battery_condition": "not_applicable_verified"};STALE={"revision": 1, "price": 103.51, "quality_assurance": False, "long_term_contract_months": 0, "status": "superseded"};PRESERVED=["seller long-term-contract priority", "seller production-demand balance", "buyer price-and-quality priority", "source-stated battery condition explicitly dispositioned"];EVIDENCE='dd75f6b18b97c8948884106de2ffd76c979fa0e4c85117561f2a14edb0d34cad'
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
