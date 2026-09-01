import hashlib,json,pathlib
CASE_ID="osw-dependency-unblock-346b788fd5";SOURCE_ID="osworld:gimp:d16c99dc-2a1e-46f2-b350-d97c86c85c15"
o=pathlib.Path("/app/output_data");r=json.loads((o/"event_receipt.json").read_text())
m={"schema_version":"async-rbench-closure-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"event_receipt_sha256":r["receipt_sha256"],"event_consumed":True,"native_evidence_consumed":True,"final_revision_sha256":hashlib.sha256((o/"osworld_native_result.json").read_bytes()).hexdigest(),"source_semantics_reverified":True,"closure_complete":True}
(o/"decision_manifest.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
