from __future__ import annotations
import hashlib, json, pathlib, subprocess
OUT=pathlib.Path('/app/output_data'); CASE_ID='swe-dependency-unblock-3f6d310987'; SOURCE_ID='sympy__sympy-24066'; BASE='514579c655bf22e2af14f0743376ae1d7befe345'

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

def test_native_pytest_01_test_quantity_definition():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_Quantity_definition'])

def test_native_pytest_02_test_quantity_eq():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_Quantity_eq'])

def test_native_pytest_03_test_abbrev():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_abbrev'])

def test_native_pytest_04_test_add_sub():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_add_sub'])

def test_native_pytest_05_test_convert_to():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_convert_to'])

def test_native_pytest_06_test_eq():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_eq'])

def test_native_pytest_07_test_issue_24062():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_issue_24062'])

def test_native_pytest_08_test_print():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_print'])

def test_native_pytest_09_test_str_repr():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'bin/test', 'sympy/physics/units/tests/test_quantities.py', '-k', 'test_str_repr'])
