from __future__ import annotations
import json,pathlib,re
O=pathlib.Path('/app/output_data');F=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json');SOURCE='research:064';CASE='mab-late-constraint-e4199e525d';ANCHORS=["hierarchical and modular policy", "low-level skill policies", "high-level controller", "skill descriptors"];DATASETS=["held-out unseen-human match trajectories", "spin- and velocity-stratified robot table-tennis trials", "simulation-to-real skill rollouts"];METRICS=["point win rate", "return success rate", "target error", "decision latency", "calibration error", "safety constraint violations", "adaptation regret"];PRESERVED=["competitive table tennis needs high-speed motion and precise control", "strategy and physical execution are coupled", "skill strengths and limitations are collected offline and online"];EVIDENCE='21ed3a65995866f7e280da99819dd6f02729b538e58e62e3a5252c2f16ba2262'
def t():return (O/'research_proposal.md').read_text()
def c():return json.loads((O/'research_closure.json').read_text())
def test_native_binding():
 n=json.loads(F.read_text());assert n['case_id']==CASE and n['source_task_id']==SOURCE and n['native_evaluator_method'].endswith('Evaluator.evaluate_task_research') and n['passed'] and min(n['native_evaluator_metrics'].values())>=4
def test_exact_fiveq():
 x=t();q1=x.split('**[Question 1]')[1].split('**[Question 2]')[0].split('**',1)[1];assert len(re.findall(r'\*\*\[Question [1-5]\]',x))==5 and q1.count('?')==1
def test_problem_anchor():
 x=t().lower();assert 'unseen human' in x and 'table tennis' in x
def test_method_anchor():
 x=t().lower();assert all(a.lower() in x for a in ['risk-calibrated','opponent adaptation','confidence-aware fallback'])
def test_evaluation_plan():
 x=t().lower();assert all(a.lower() in x for a in DATASETS) and all(a.lower() in x for a in METRICS)
def test_schema_and_preservation():
 x=c();assert set(x)=={'schema_version','case_id','source_task_id','event_receipt_sha256','native_evidence_sha256','proposal_sha256','preserved_source_facts','source_semantics_reverified','closure_complete'} and x['native_evidence_sha256']==EVIDENCE and x['preserved_source_facts']==PRESERVED
