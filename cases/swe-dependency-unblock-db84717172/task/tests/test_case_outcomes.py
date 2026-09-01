from __future__ import annotations
import hashlib, json, pathlib, subprocess
OUT=pathlib.Path('/app/output_data'); CASE_ID='swe-dependency-unblock-db84717172'; SOURCE_ID='django__django-12262'; BASE='69331bb851c34f05bc77e9fc24020fe6908b9cd5'

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

def test_native_django_01_template_tests_test_custom_customfiltertes():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'tests/runtests.py', '--verbosity', '0', 'template_tests.test_custom.CustomFilterTests'])

def test_native_django_02_template_tests_test_custom_inclusiontagtes():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'tests/runtests.py', '--verbosity', '0', 'template_tests.test_custom.InclusionTagTests'])

def test_native_django_03_template_tests_test_custom_simpletagtests():
    _run_native(['/opt/miniconda3/envs/testbed/bin/python', 'tests/runtests.py', '--verbosity', '0', 'template_tests.test_custom.SimpleTagTests'])
