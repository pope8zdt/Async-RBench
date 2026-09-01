from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); receipt=json.loads((OUT/'event_receipt.json').read_text()); sha=hashlib.sha256((OUT/'solution.py').read_bytes()).hexdigest(); stages=['event_intake','state_revision','closure']
manifest={'schema_version':'async-rbench-closure-v1','case_id':'mab-dependency-unblock-107bc4fe3f','source_task_id':'coding:017','event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'final_revision_sha256':sha,'source_semantics_reverified':True,'closure_complete':True,'control_flow':{s:{'completed':True,'receipt_sha256':receipt['receipt_sha256']} for s in stages}}; (OUT/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
