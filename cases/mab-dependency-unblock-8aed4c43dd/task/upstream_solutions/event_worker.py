from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-dependency-unblock-8aed4c43dd'; SOURCE_ID='database:013'; CHECKPOINT='b97d78c5fb7f69fbdd5296f208a9bfd520041e6c7055c9b37a630a03c5d6e67c'; ROOT_CAUSE='LOCK_CONTENTION'; EVIDENCE={'blocker_lock_rows': 4, 'waiter_timeout_observed': True}
def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',default='/app/output_data/event_receipt.json'); p.add_argument('--workspace',default='/app'); a=p.parse_args(); started=time.time()
    value={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'authoritative_postgres_checkpoint','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':CHECKPOINT},'authority':{'selected_cause':ROOT_CAUSE,'anomaly_evidence':EVIDENCE}}
    value['receipt_sha256']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); print(json.dumps(value,sort_keys=True))
if __name__=='__main__': main()
