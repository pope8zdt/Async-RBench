from __future__ import annotations
import argparse, hashlib, json, pathlib, time
CASE_ID='mab-dependency-unblock-031ed6f5bc'; SOURCE_ID='coding:087'; EVENT='validation_contract_replayed'; EVENT_THEME='duplicate_or_replayed_completion'; MEANING='A replayed validation completion is deduplicated and cannot duplicate transformation or export side effects.'; AUTHORITY={'contract': 'row_validation_v3', 'required_fields': ['id', 'amount'], 'error_codes': ['missing_id', 'invalid_amount'], 'delivery_count': 2, 'idempotency_key': 'validation-batch-87'}
PROBE_PATHS=['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']
def digest(path):
    p=pathlib.Path(path); return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--workspace',default='/app'); ap.add_argument('--output',default='/app/output_data/event_receipt.json'); args=ap.parse_args(); started=time.time()
    probes={p:digest(p) for p in PROBE_PATHS}
    payload={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':EVENT_THEME,'meaning':MEANING,'authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'evaluator-owned authority completed','workspace_revision_before':digest('/app/output_data/provisional_checkpoint.json'),'workspace_revision_after':digest('/app/output_data/solution.py'),'probes':probes}
    payload['receipt_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); return 0
if __name__=='__main__': raise SystemExit(main())
