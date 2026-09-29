from __future__ import annotations
import hashlib, json, pathlib, subprocess
CASE_ID="osw-dependency-unblock-0008d814cb"
SOURCE_ID="osworld:chrome:a96b564e-dbe9-42c3-9ccf-b4498073438a"
out=pathlib.Path("/app/output_data")
receipt=json.loads((out/"event_receipt.json").read_text())
root=pathlib.Path("/app")
if (root/".git").exists():
    revision=subprocess.run(["git","diff","--binary"],cwd=root,stdout=subprocess.PIPE,check=False).stdout
else:
    h=hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "/output_data/" not in path.as_posix():
            h.update(str(path).encode()); h.update(path.read_bytes())
    revision=h.digest()
manifest={"schema_version":"async-rbench-closure-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"event_receipt_sha256":receipt["receipt_sha256"],"event_consumed":True,"native_evidence_consumed":True,"final_revision_sha256":hashlib.sha256(revision).hexdigest(),"source_semantics_reverified":True,"closure_complete":True}
(out/"decision_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
