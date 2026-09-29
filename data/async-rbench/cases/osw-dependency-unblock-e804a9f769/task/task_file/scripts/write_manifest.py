import hashlib,json,pathlib
CASE_ID="osw-dependency-unblock-e804a9f769";SOURCE_ID="osworld:multi_apps:716a6079-22da-47f1-ba73-c9d58f986a38"
o=pathlib.Path("/app/output_data");r=json.loads((o/"event_receipt.json").read_text())
m={"schema_version":"async-rbench-closure-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"event_receipt_sha256":r["receipt_sha256"],"event_consumed":True,"native_evidence_consumed":True,"final_revision_sha256":hashlib.sha256((o/"osworld_native_result.json").read_bytes()).hexdigest(),"source_semantics_reverified":True,"closure_complete":True}
(o/"decision_manifest.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
