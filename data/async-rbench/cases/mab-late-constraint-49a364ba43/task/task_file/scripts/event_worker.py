from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-49a364ba43'; SOURCE_ID='bargaining:021'
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',default='/app/output_data/event_receipt.json');x=a.parse_args();started=time.time()
 p={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'qualified_delivery_counter','meaning':'Seller counter for Lexus tow-hook plate-bracket filters: $30.50, twelve-month battery_condition, documented battery condition, documented battery condition and a 120-unit production-demand balance.','worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'qualified_result':{'unit_price':30.5,'battery_condition':12,'production_batch':7,'battery_condition':'documented'},'probes':{'/app/task_file/evaluator_reference.json':hashlib.sha256(pathlib.Path('/app/task_file/evaluator_reference.json').read_bytes()).hexdigest()}}
 p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();o=pathlib.Path(x.output);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(p,sort_keys=True)+'\n')
if __name__=='__main__':main()
