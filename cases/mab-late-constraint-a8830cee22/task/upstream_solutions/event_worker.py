import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-a8830cee22'; SOURCE_ID='bargaining:025'; EVENT='after_sales_contract_confirmed'; THEME='delayed_authoritative_result'; AUTHORITY={'unit_price': 11.5, 'warranty_months': 18, 'support_response_days': 2, 'contract_months': 24}
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time()
    probes={p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}
    data={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':THEME,'meaning':'The service authority confirms $11.50 per basket, an 18-month warranty, two-business-day support, and a 24-month purchasing commitment.','authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':probes}
    data['receipt_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    pathlib.Path(args.output).write_text(json.dumps(data,sort_keys=True)+'\n')
if __name__=='__main__': main()
