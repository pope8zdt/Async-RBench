import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-ae2fc903e5'; SOURCE_ID='bargaining:026'; EVENT='condition_and_shipping_certificate_delivered'; THEME='delayed_authoritative_result'; AUTHORITY={'unit_price': 57.79, 'condition_check': 'passed', 'coverage_months': 12, 'shipping_days': 6}
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time()
    probes={p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}
    data={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':THEME,'meaning':'A condition certificate confirms the changing station passed inspection, carries 12 months of coverage, ships in six days, and is offered at $57.79.','authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':probes}
    data['receipt_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    pathlib.Path(args.output).write_text(json.dumps(data,sort_keys=True)+'\n')
if __name__=='__main__': main()
