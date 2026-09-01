import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-02f32d73a5'; SOURCE_ID='bargaining:027'; EVENT='production_battery_scope_added'; THEME='task_scope_or_dependency_change'; AUTHORITY={'minimum_batch': 200, 'unit_price': 6.2, 'battery_test': 'passed', 'premium_feature': 'usb_rechargeable', 'lead_time_days': 10}
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time()
    probes={p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}
    data={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':THEME,'meaning':'Production adds a 200-unit minimum, $6.20 unit price, ten-day lead time, passed battery test, and USB-rechargeable feature requirement.','authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':probes}
    data['receipt_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    pathlib.Path(args.output).write_text(json.dumps(data,sort_keys=True)+'\n')
if __name__=='__main__': main()
