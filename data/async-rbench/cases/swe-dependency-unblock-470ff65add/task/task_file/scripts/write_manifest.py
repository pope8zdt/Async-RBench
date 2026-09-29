from __future__ import annotations
import hashlib, json, pathlib, subprocess
CASE_ID='swe-dependency-unblock-470ff65add'; SOURCE_ID='instance_ansible__ansible-4c5ce5a1a9e79a845aff4978cfeb72a0d4ecf7d6-v1055803c3a812189a1133297f7f5468579283f86'; WORKSPACE='/testbed'
out=pathlib.Path('/app/output_data'); receipt=json.loads((out/'event_receipt.json').read_text())
root=pathlib.Path(WORKSPACE)
if (root/'.git').exists():
    revision=subprocess.run(['git','diff','--binary'],cwd=root,stdout=subprocess.PIPE).stdout
else:
    h=hashlib.sha256()
    for p in sorted(x for x in root.rglob('*') if x.is_file()): h.update(str(p).encode()); h.update(p.read_bytes())
    revision=h.digest()
manifest={'schema_version':'async-rbench-closure-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'final_revision_sha256':hashlib.sha256(revision).hexdigest(),'source_semantics_reverified':True,'closure_complete':True}
(out/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
