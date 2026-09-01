from __future__ import annotations
import hashlib, json, pathlib, subprocess
OUT=pathlib.Path('/app/output_data'); CASE_ID='swe-late-constraint-17e23e3eb3'; SOURCE_ID='sympy__sympy-22714'; BASE='3ff4717b6aef6086e78f01cdfa06f64ae23aed7e'

def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); actual=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert claimed==actual; assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID

def test_independent_worker_completed_with_observable_probes():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_finished_at']>=p['worker_started_at']; assert p['worker_exit_code']==0; assert p['probes']; assert any(v is not None for v in p['probes'].values())

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

def test_native_pytest_01_test_point2d():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_Point2D'])

def test_native_pytest_02_test_normalize_dimension():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test__normalize_dimension'])

def test_native_pytest_03_test_arguments():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_arguments'])

def test_native_pytest_04_test_concyclic_doctest_bug():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_concyclic_doctest_bug'])

def test_native_pytest_05_test_dot():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_dot'])

def test_native_pytest_06_test_issue_11617():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_issue_11617'])

def test_native_pytest_07_test_issue_22684():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_issue_22684'])

def test_native_pytest_08_test_issue_9214():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_issue_9214'])

def test_native_pytest_09_test_point():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_point'])

def test_native_pytest_10_test_point3d():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_point3D'])

def test_native_pytest_11_test_transform():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_transform'])

def test_native_pytest_12_test_unit():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/geometry/tests/test_point.py', '-k', 'test_unit'])
