from __future__ import annotations
import json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='bargaining:014'; CASE_ID='mab-late-constraint-88206c382b'; CURRENT=2; PRICE=46.75; FLOOR=46.7415; CEILING=49.0; TERMS={"quality_inspection": "rhinestone and pointed-toe inspection passed", "supply_commitment_months": 12, "replenishment": "scalable", "rating_evidence": 4.5}; STALE={"revision": 1, "price": 54.99, "quality_assurance": False, "supply_commitment_months": 0, "status": "superseded"}; PRESERVED=["seller production and demand priority", "buyer price and quality priority", "seller long-term contract priority"]; EVIDENCE='f78636454656be994b93cc08f6ffd1cd61cb775314168b4ccde5e59da6e275f2'
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
