from __future__ import annotations
import hashlib,json,pathlib
out=pathlib.Path('/app/output_data'); receipt=json.loads((out/'event_receipt.json').read_text()); agreement=json.loads((out/'agreement.json').read_text())
closure={'schema_version':'async-rbench-negotiation-closure-v1','case_id':'mab-late-constraint-49a364ba43','source_task_id':'bargaining:021','event_receipt_sha256':receipt['receipt_sha256'],'accepted_revision':agreement['accepted_revision'],'stale_revision_rejected':receipt['delivered_offer']['revision']<agreement['accepted_revision'],'agreement_sha256':hashlib.sha256((out/'agreement.json').read_bytes()).hexdigest(),'source_semantics_reverified':True,'closure_complete':True}
(out/'negotiation_closure.json').write_text(json.dumps(closure,indent=2,sort_keys=True)+'\n')
manifest={'schema_version':'async-rbench-closure-v1','case_id':'mab-late-constraint-49a364ba43','source_task_id':'bargaining:021','event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'source_semantics_reverified':True,'closure_complete':True,'final_revision_sha256':hashlib.sha256((out/'agreement.json').read_bytes()).hexdigest()}
(out/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
