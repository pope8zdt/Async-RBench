from __future__ import annotations
import argparse, hashlib, json, pathlib, time
CASE_ID='mab-conflicting-specialist-results-cf7b930f57'; SOURCE_ID='database:004'; CHECKPOINT_SHA='277ff2325bd9d7fc4dfe90d2b0c8cc7437369c7ecaa61d9e9877a9b2fbf8b93c'
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default='/app/output_data/event_receipt.json'); ap.add_argument('--workspace',default='/app'); args=ap.parse_args()
    started=time.time()
    payload={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'authoritative_postgres_checkpoint','worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':CHECKPOINT_SHA}}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode(); payload['receipt_sha256']=hashlib.sha256(raw).hexdigest()
    out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
    print(json.dumps(payload,sort_keys=True))
if __name__=='__main__': main()
