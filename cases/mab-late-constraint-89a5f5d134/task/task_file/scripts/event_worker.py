from __future__ import annotations
import argparse, hashlib, json, pathlib, time

CASE_ID = 'mab-late-constraint-89a5f5d134'
SOURCE_ID = 'bargaining:015'
STALE = {'revision': 1, 'price': 11.99, 'compatibility': 'unverified', 'bundled_logistics': False, 'status': 'superseded'}
EVIDENCE = 'aa80cc353bca6a8aeba33935ab585e7da8eb2c0da1e349f643626fd212eb092c'

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', default='/app/output_data/event_receipt.json'); parser.add_argument('--workspace', default='/app'); args = parser.parse_args()
    started = time.time()
    receipt = {'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'late_superseded_offer_delivery','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'delivered_offer':STALE,'accepted_current_revision':2,'classification':'late_and_superseded','native_evidence_sha256':EVIDENCE}
    receipt['receipt_sha256'] = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    output = pathlib.Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n'); print(json.dumps(receipt, sort_keys=True))

if __name__ == '__main__': main()
