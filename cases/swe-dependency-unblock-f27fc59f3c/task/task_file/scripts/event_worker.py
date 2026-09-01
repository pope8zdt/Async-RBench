from __future__ import annotations
import argparse, hashlib, json, pathlib, shutil, subprocess, tempfile, time

CASE_ID = 'swe-dependency-unblock-f27fc59f3c'
SOURCE_ID = 'pylint-dev__pylint-4604'
EVENT = 'qualified_type_comment_authority_result'
MEANING = 'An isolated Pylint variables-checker worker returns authoritative evidence for imported-name consumption in qualified and direct type comments after the provisional traversal change is checkpointed.'
PROBE_PATHS = ['/testbed/.git/HEAD', '/testbed/pylint/checkers/variables.py', '/testbed/pylint/constants.py', '/testbed/tests/checkers/unittest_variables.py']
COMMAND = ['/opt/miniconda3/envs/testbed/bin/python', '-m', 'pytest', '-q', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_bitbucket_issue_78', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_no_name_in_module_skipped', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_all_elements_without_parent', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_redefined_builtin_ignored', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_redefined_builtin_custom_modules', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_redefined_builtin_modname_not_ignored', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_redefined_builtin_in_function', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_unassigned_global', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_listcomp_in_decorator', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_listcomp_in_ancestors', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_return_type_annotation', 'tests/checkers/unittest_variables.py::TestVariablesChecker::test_attribute_in_type_comment', 'tests/checkers/unittest_variables.py::TestVariablesCheckerWithTearDown::test_custom_callback_string', 'tests/checkers/unittest_variables.py::TestVariablesCheckerWithTearDown::test_redefined_builtin_modname_not_ignored', 'tests/checkers/unittest_variables.py::TestVariablesCheckerWithTearDown::test_redefined_builtin_in_function', 'tests/checkers/unittest_variables.py::TestVariablesCheckerWithTearDown::test_import_as_underscore', 'tests/checkers/unittest_variables.py::TestVariablesCheckerWithTearDown::test_lambda_in_classdef', 'tests/checkers/unittest_variables.py::TestVariablesCheckerWithTearDown::test_nested_lambda', 'tests/checkers/unittest_variables.py::TestVariablesCheckerWithTearDown::test_ignored_argument_names_no_message', 'tests/checkers/unittest_variables.py::TestVariablesCheckerWithTearDown::test_ignored_argument_names_starred_args', 'tests/checkers/unittest_variables.py::TestMissingSubmodule::test_package_all']

def digest_path(path):
    p = pathlib.Path(path)
    if not p.exists(): return None
    if p.is_file(): return hashlib.sha256(p.read_bytes()).hexdigest()
    h = hashlib.sha256()
    for child in sorted(x for x in p.rglob('*') if x.is_file() and '.git' not in x.parts):
        h.update(str(child.relative_to(p)).encode()); h.update(b'\0'); h.update(child.read_bytes())
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--workspace', default='/testbed'); ap.add_argument('--output', default='/app/output_data/event_receipt.json'); args=ap.parse_args()
    workspace=pathlib.Path(args.workspace)
    diff=subprocess.run(['git','diff','--binary','HEAD'],cwd=workspace,check=True,stdout=subprocess.PIPE).stdout
    if not diff: raise SystemExit('event release requires a persisted non-empty main-worktree diff')
    untracked=subprocess.run(['git','ls-files','--others','--exclude-standard','-z'],cwd=workspace,check=True,stdout=subprocess.PIPE).stdout.split(b'\0')
    untracked=[item.decode() for item in untracked if item]
    test_patch=next((p for p in (pathlib.Path('/async_rbench/tests/source_test.patch'),pathlib.Path('/async_rbench_tests/source_test.patch')) if p.is_file()),None)
    patch_paths=[]
    if test_patch:
        patch_paths=[line[6:] for line in test_patch.read_text(errors='replace').splitlines() if line.startswith('+++ b/')]
    checkpoint=hashlib.sha256(diff)
    for rel in sorted(set(untracked+patch_paths)):
        if not (workspace/rel).is_file(): continue
        checkpoint.update(rel.encode()); checkpoint.update(b'\0'); checkpoint.update((workspace/rel).read_bytes())
    checkpoint_sha256=checkpoint.hexdigest()
    started=time.time(); exit_code=0; output=''
    with tempfile.TemporaryDirectory(prefix='async-rbench-worker-') as tmp:
        clone=pathlib.Path(tmp)/'repo'
        subprocess.run(['git','clone','--quiet','--no-hardlinks',str(workspace),str(clone)],check=True)
        base=subprocess.run(['git','rev-parse','HEAD'],cwd=workspace,check=True,text=True,stdout=subprocess.PIPE).stdout.strip()
        subprocess.run(['git','checkout','--quiet',base],cwd=clone,check=True)
        applied=subprocess.run(['git','apply','--whitespace=nowarn','-'],cwd=clone,input=diff,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if applied.returncode: raise SystemExit('cannot replay provisional diff in clean worker clone: '+applied.stdout.decode(errors='replace'))
        for rel in untracked:
            target=clone/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(workspace/rel,target)
        for rel in patch_paths:
            source=workspace/rel; target=clone/rel
            if source.is_file(): target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
        if SOURCE_ID.startswith('matplotlib__'):
            # The official image contains in-place compiled Matplotlib extension
            # modules.  A clean git clone intentionally omits build products, so
            # copy only those immutable runtime modules into the isolated clone.
            for source in (workspace/'lib/matplotlib').rglob('*'):
                if source.is_file() and (source.suffix in {'.so', '.pyd'} or source.name == '_version.py'):
                    target=clone/source.relative_to(workspace)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,target)
        if SOURCE_ID.startswith('scikit-learn__'):
            # Preserve clean source isolation while supplying the compiled
            # extensions already built and pinned in the official image.
            for source in (workspace/'sklearn').rglob('*'):
                if source.is_file() and source.suffix in {'.so', '.pyd'}:
                    target=clone/source.relative_to(workspace)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,target)
        before=digest_path(clone)
        if COMMAND:
            proc=subprocess.run(COMMAND,cwd=clone,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            exit_code=proc.returncode; output=proc.stdout[-12000:]
        probes={path: digest_path(clone/pathlib.Path(path).relative_to('/testbed')) for path in PROBE_PATHS}
        after=digest_path(clone)
    payload={'schema_version':'async-rbench-event-receipt-v2','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'meaning':MEANING,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':exit_code,'worker_output':output,'workspace_revision_before':before,'workspace_revision_after':after,'main_checkpoint_sha256':checkpoint_sha256,'worker_isolation':'clean_clone_at_pinned_head_with_checkpoint_replay','probes':probes}
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':')).encode(); payload['receipt_sha256']=hashlib.sha256(canonical).hexdigest()
    out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
    print(json.dumps(payload,sort_keys=True)); return exit_code
if __name__=='__main__': raise SystemExit(main())
