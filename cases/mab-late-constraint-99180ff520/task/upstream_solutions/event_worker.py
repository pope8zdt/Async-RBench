import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-99180ff520'; SOURCE_ID='bargaining:023'; EVENT='verified_delivery_quality_counter'; THEME='late_or_out_of_order_superseded_result'; AUTHORITY={'seller_counter': {'unit_price': 14.25, 'condition': 'new', 'delivery_days': 3}, 'supersedes': {'unit_price': 12.0, 'delivery': 'unverified'}}
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time()
    probes={p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}
    data={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':THEME,'meaning':'The current seller counter verifies a new PS4 game at $14.25 with three-day delivery and supersedes the unsupported $12 offer.','authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':probes}
    data['receipt_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    pathlib.Path(args.output).write_text(json.dumps(data,sort_keys=True)+'\n')
if __name__=='__main__': main()
