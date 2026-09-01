from __future__ import annotations
import hashlib, json, pathlib, subprocess
OUT=pathlib.Path('/app/output_data'); CASE_ID='swe-late-test-evidence-9f62f0f149'; SOURCE_ID='instance_ansible__ansible-bf98f031f3f5af31a2d78dc2f0a58fe92ebae0bb-v1055803c3a812189a1133297f7f5468579283f86'; BASE='17332532973343248297e3d3c746738d1f3b2f56'

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

def test_native_sanitize_keys_changed():
    _run_native(['python3', '-m', 'pytest', '-q', 'test/units/module_utils/basic/test_sanitize_keys.py::test_sanitize_keys_non_dict_types', 'test/units/module_utils/basic/test_sanitize_keys.py::test_sanitize_keys_with_ignores', 'test/units/module_utils/basic/test_sanitize_keys.py::test_sanitize_keys_dict', 'test/units/module_utils/basic/test_no_log.py::TestRemoveValues::test_strings_to_remove'])

def test_native_no_log_preserved():
    _run_native(['python3', '-m', 'pytest', '-q', 'test/units/module_utils/basic/test_no_log.py::TestRemoveValues::test_no_removal', 'test/units/module_utils/basic/test_no_log.py::TestRemoveValues::test_hit_recursion_limit'])
