import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-1e1fa7c00b'; SOURCE_ID='bargaining:029'; EVENT='freight_finish_counter_supersedes_quote'; THEME='late_or_out_of_order_superseded_result'; AUTHORITY={'current_counter': {'unit_price': 25.49, 'finish': 'heavy_duty_rustic', 'delivery_days': 7}, 'supersedes': {'unit_price': 22.0, 'freight': 'unverified'}}
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time()
    probes={p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}
    data={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':THEME,'meaning':'The current freight-backed counter offers the heavy-duty rustic turtle doorstop at $25.49 with seven-day delivery and supersedes the unverified $22 quote.','authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':probes}
    data['receipt_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    pathlib.Path(args.output).write_text(json.dumps(data,sort_keys=True)+'\n')
if __name__=='__main__': main()
