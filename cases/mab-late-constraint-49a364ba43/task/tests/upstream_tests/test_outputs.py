from __future__ import annotations
import json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='bargaining:021'; CASE_ID='mab-late-constraint-49a364ba43'; CURRENT=2; PRICE=18.27; TARGET=21.49; FLOOR=18.2665; BASELINE=18.0
TERMS={"battery_condition":"not_applicable_verified","fitment":"Lexus no-drill fitment verified","production_demand_balance":"seller-confirmed","seller_discount_cap_pct":15}
STALE={"revision":1,"price":21.49,"battery_condition":"unverified","production_demand_balance":"unconfirmed","status":"superseded"}
PRESERVED=["seller $21.49 target with 15 percent discount limit","buyer $18 baseline budget","source-stated battery condition and production-demand balance"]
def agreement(): return json.loads((OUT/'agreement.json').read_text())
def ledger(): return json.loads((OUT/'negotiation_ledger.json').read_text())
def test_native_world_evaluator_binding():
 n=json.loads(FIX.read_text()); assert n['case_id']==CASE_ID and n['source_task_id']==SOURCE_ID and n['native_evaluator_method'].endswith('Evaluator.evaluate_code_quality') and n['passed']; assert min(n['native_evaluator_metrics'].values())>=4
def test_current_revision_is_accepted():
 a=agreement(); l=ledger(); assert a['accepted_revision']==CURRENT==l['accepted_revision'] and l['current_offer']['price_usd']==PRICE
def test_price_respects_source_discount_and_budget():
 a=agreement(); assert a['seller_target_usd']==TARGET and a['seller_floor_usd']==FLOOR and a['buyer_baseline_usd']==BASELINE and FLOOR<=a['price_usd']<=18.27
def test_product_specific_terms():
 a=agreement(); assert a['terms']==TERMS and a['agreement_reached']
def test_stale_offer_is_excluded():
 l=ledger(); assert l['superseded_revisions']==[STALE] and STALE['revision']<l['accepted_revision'] and l['current_offer']['price_usd']!=STALE['price']
def test_schema_evidence_and_preservation():
 a=agreement(); l=ledger(); assert set(a)=={'source_task_id','product','accepted_revision','price_usd','seller_target_usd','seller_floor_usd','buyer_baseline_usd','terms','agreement_reached','preserved_priorities','native_evidence_sha256'}; assert a['preserved_priorities']==PRESERVED and l['chronology_verified']
def test_lexus_tow_hook_agreement_values(): test_current_revision_is_accepted(); test_price_respects_source_discount_and_budget()
def test_source_native_evaluator_binding(): test_native_world_evaluator_binding()
def test_receipt_and_closure_lineage():
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert r['classification']=='late_and_superseded' and m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['closure_complete']
def test_buyer_delivery_and_battery_condition_are_preserved(): test_product_specific_terms()
