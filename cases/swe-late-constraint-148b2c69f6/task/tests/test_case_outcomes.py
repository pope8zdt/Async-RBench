from __future__ import annotations
import hashlib, json, pathlib, subprocess
OUT=pathlib.Path('/app/output_data'); CASE_ID='swe-late-constraint-148b2c69f6'; SOURCE_ID='scikit-learn__scikit-learn-12973'; BASE='a7b8b9e9e16d4e15fabda5ae615086c2e1c47d8a'

def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); actual=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert claimed==actual; assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID

def test_independent_worker_completed_with_observable_probes():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_finished_at']>=p['worker_started_at']; assert p['worker_exit_code']==0; assert p['probes']; assert any(v is not None for v in p['probes'].values()); output=p.get('worker_output','').lower(); assert "could not import 'mock'" not in output; assert ' skipped' not in output

def test_final_closure_consumes_exact_event_receipt():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256']; assert m['event_consumed'] is True and m['source_semantics_reverified'] is True and m['closure_complete'] is True

def test_pinned_source_revision_is_preserved():
    if BASE and pathlib.Path('/testbed/.git').exists():
        subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd='/testbed',check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    else: assert SOURCE_ID

def _run_native(command):
    cwd='/testbed' if pathlib.Path('/testbed').exists() else '/app'
    r=subprocess.run(command,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    assert r.returncode==0, r.stdout[-12000:]

def test_native_pytest_01_sklearn_linear_model_tests_test_least_angl():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', '-m', 'pytest', '-q', 'sklearn/linear_model/tests/test_least_angle.py::test_lasso_lars_fit_copyX_behaviour[False]'])

def test_native_pytest_02_sklearn_linear_model_tests_test_least_angl():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', '-m', 'pytest', '-q', 'sklearn/linear_model/tests/test_least_angle.py::test_simple', 'sklearn/linear_model/tests/test_least_angle.py::test_simple_precomputed', 'sklearn/linear_model/tests/test_least_angle.py::test_all_precomputed', 'sklearn/linear_model/tests/test_least_angle.py::test_lars_lstsq', 'sklearn/linear_model/tests/test_least_angle.py::test_lasso_gives_lstsq_solution', 'sklearn/linear_model/tests/test_least_angle.py::test_collinearity', 'sklearn/linear_model/tests/test_least_angle.py::test_no_path', 'sklearn/linear_model/tests/test_least_angle.py::test_no_path_precomputed'])
