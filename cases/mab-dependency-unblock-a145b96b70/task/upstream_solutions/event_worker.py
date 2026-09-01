from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-dependency-unblock-a145b96b70'; SOURCE_ID='database:023'; CHECKPOINT='834bd92f8f348bbf0505f531ac223cde7a5b01d4f911603df5dd784ea44906e4'; ROOT_CAUSE='INSERT_LARGE_DATA'; EVIDENCE={'bytes': 1556480, 'row_count': 5000}
def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',default='/app/output_data/event_receipt.json'); p.add_argument('--workspace',default='/app'); a=p.parse_args(); started=time.time()
    value={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'authoritative_postgres_checkpoint','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':CHECKPOINT},'authority':{'selected_cause':ROOT_CAUSE,'anomaly_evidence':EVIDENCE}}
    value['receipt_sha256']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); print(json.dumps(value,sort_keys=True))
if __name__=='__main__': main()
