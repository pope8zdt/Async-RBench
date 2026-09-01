from __future__ import annotations
import hashlib,json,pathlib,re
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='research:051'; CASE_ID='mab-late-constraint-383afddcb0'; ANCHORS=["PlainMamba", "continuous 2D scanning", "spatial adjacency", "token-dependent B C and Delta"]; DATASETS=["ImageNet-1K", "ADE20K", "COCO"]; METRICS=["top-1 accuracy", "mIoU", "AP", "FLOPs", "latency", "scan-discontinuity rate"]; PRESERVED=["plain encoders are reusable", "selective scan is token dependent", "adjacent scans avoid spatial discontinuity"]; EVIDENCE='5d2bb6319923a931be0f9eeef35a1e253f6611526e0370942c419dae7572e6a9'
def text(): return (OUT/'research_proposal.md').read_text()
def closure(): return json.loads((OUT/'research_closure.json').read_text())
def test_native_research_evaluator_binding():
    n=json.loads(FIX.read_text()); assert n['case_id']==CASE_ID and n['source_task_id']==SOURCE_ID and n['native_evaluator_method'].endswith('Evaluator.evaluate_task_research') and n['passed'] and min(n['native_evaluator_metrics'].values())>=4
def test_exact_five_question_structure():
    t=text(); assert len(re.findall(r'\*\*\[Question [1-5]\]',t))==5; q1=t.split('**[Question 1]')[1].split('**[Question 2]')[0]; assert q1.count('?')==1
def test_problem_is_source_specific():
    low=text().lower(); assert all(a.lower() in low for a in ANCHORS[:2])
def test_method_matches_delayed_authority():
    r=json.loads((OUT/'event_receipt.json').read_text()); low=text().lower(); assert r['authority']['method'].lower() in low
def test_datasets_and_metrics_are_task_specific():
    low=text().lower(); assert all(x.lower() in low for x in DATASETS) and all(x.lower() in low for x in METRICS)
def test_schema_digests_and_preservation():
    c=closure(); assert set(c)=={'schema_version','case_id','source_task_id','event_receipt_sha256','native_evidence_sha256','proposal_sha256','preserved_source_facts','source_semantics_reverified','closure_complete'}; assert c['native_evidence_sha256']==EVIDENCE and c['preserved_source_facts']==PRESERVED and c['source_semantics_reverified']
