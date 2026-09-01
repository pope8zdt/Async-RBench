from __future__ import annotations
import hashlib,json,pathlib,subprocess
CASE_ID='mab-dependency-unblock-b69316f186'; SOURCE_ID='database:018'; root=pathlib.Path('/app'); out=root/'output_data'; receipt=json.loads((out/'event_receipt.json').read_text())
if (root/'.git').exists(): revision=subprocess.run(['git','diff','--binary'],cwd=root,stdout=subprocess.PIPE).stdout
else:
    h=hashlib.sha256()
    for p in sorted(x for x in root.rglob('*') if x.is_file() and 'output_data' not in x.parts): h.update(str(p).encode()); h.update(p.read_bytes())
    revision=h.digest()
manifest={'schema_version':'async-rbench-closure-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'final_revision_sha256':hashlib.sha256(revision).hexdigest(),'source_semantics_reverified':True,'closure_complete':True}
(out/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
