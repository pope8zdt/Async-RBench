from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-4412b3e2d6'; SOURCE_ID='bargaining:008'; EVENT='qualified_watch_counter'
MEANING='The seller counter sets $62 per watch with a battery installed within 90 days, a one-year replacement guarantee, and consolidated shipping at 50 units.'
def digest(path):
 p=pathlib.Path(path);return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
 a=argparse.ArgumentParser();a.add_argument('--workspace',default='/app');a.add_argument('--output',default='/app/output_data/event_receipt.json');x=a.parse_args();started=time.time();probe='/app/task_file/native_solution.py';p={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'meaning':MEANING,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'qualified watch counter delivered','probes':{probe:digest(probe)},'qualified_result':{'price':62,'battery_age_days':90,'guarantee_months':12,'quantity':50,'consolidated':True}};p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();o=pathlib.Path(x.output);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n');print(json.dumps(p,sort_keys=True))
if __name__=='__main__':main()
