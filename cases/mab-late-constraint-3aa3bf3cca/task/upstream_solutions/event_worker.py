import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-3aa3bf3cca'; SOURCE_ID='bargaining:030'; EVENT='product_quality_scope_clarified'; THEME='task_scope_or_dependency_change'; AUTHORITY={'power_requirement': 'none', 'material': 'velvet_ring_holder', 'unit_price': 17.49, 'minimum_batch': 60}
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time()
    probes={p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}
    data={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':THEME,'meaning':'Product authority clarifies that the organizer has no power requirement; quality is the velvet ring holder, with a 60-unit minimum at $17.49.','authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':probes}
    data['receipt_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    pathlib.Path(args.output).write_text(json.dumps(data,sort_keys=True)+'\n')
if __name__=='__main__': main()
