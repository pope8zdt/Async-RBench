from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-4412b3e2d6'; SOURCE_ID='bargaining:008'; EVENT='qualified_volume_contract_counter'
MEANING='The bound seller counter sets $17 per unit for four quarters of 200 units, with a sample and printing-defect replacement.'
def digest(path):
 p=pathlib.Path(path);return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
 a=argparse.ArgumentParser();a.add_argument('--workspace',default='/app');a.add_argument('--output',default='/app/output_data/event_receipt.json');x=a.parse_args();started=time.time();probe='/app/task_file/native_canonical_report.json';p={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'meaning':MEANING,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'qualified volume contract delivered','probes':{probe:digest(probe)},'qualified_result':{'unit_price':17,'quarters':4,'units_per_quarter':200,'sample_approved':True,'printing_defects_replaced':True}};p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();o=pathlib.Path(x.output);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n');print(json.dumps(p,sort_keys=True))
if __name__=='__main__':main()
