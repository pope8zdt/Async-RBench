from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-dependency-unblock-720c69400a'; SOURCE_ID='coding:004'; EVENT='retailer_quote_worker_recovered'; EVENT_THEME='child_failure_or_implicit_error'; MEANING='Recovered multi-retailer comparison replaces scalar prices while user thresholds, groups, shared alerts, and notification preferences remain intact.'; AUTHORITY={'contract': 'normalized_quote_v2', 'fields': ['retailer', 'product_id', 'price', 'currency', 'available', 'observed_at'], 'selection': 'fresh_available_converted_minimum', 'recovery': 'redelegated'}
def digest(path):
    p=pathlib.Path(path); return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--workspace',default='/app'); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time(); probes={p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}
    payload={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':EVENT_THEME,'meaning':MEANING,'authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'task-specific evaluator authority completed','workspace_revision_before':probes['/app/output_data/provisional_checkpoint.json'],'workspace_revision_after':probes['/app/output_data/solution.py'],'probes':probes}
    payload['receipt_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); return 0
if __name__=='__main__': raise SystemExit(main())
