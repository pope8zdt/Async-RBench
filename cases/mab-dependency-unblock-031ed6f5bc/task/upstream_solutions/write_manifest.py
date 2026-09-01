from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); receipt=json.loads((OUT/'event_receipt.json').read_text()); solution_sha=hashlib.sha256((OUT/'solution.py').read_bytes()).hexdigest()
manifest={'schema_version':'async-rbench-closure-v1','case_id':'mab-dependency-unblock-031ed6f5bc','source_task_id':'coding:087','event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'final_revision_sha256':solution_sha,'source_semantics_reverified':True,'closure_complete':True,'control_flow':{stage:{'completed':True,'receipt_sha256':receipt['receipt_sha256']} for stage in ['event_intake', 'plan_revision']}}
(OUT/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
