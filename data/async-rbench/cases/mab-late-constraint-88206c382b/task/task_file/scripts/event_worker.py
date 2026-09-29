from __future__ import annotations
import argparse, hashlib, json, pathlib, time

CASE_ID = 'mab-late-constraint-88206c382b'
SOURCE_ID = 'bargaining:014'
STALE = {'revision': 1, 'price': 54.99, 'quality_assurance': False, 'supply_commitment_months': 0, 'status': 'superseded'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='/app/output_data/event_receipt.json')
    parser.add_argument('--workspace', default='/app')
    args = parser.parse_args()
    started = time.time()
    receipt = {
        'schema_version': 'async-rbench-event-receipt-v1', 'case_id': CASE_ID,
        'source_task_id': SOURCE_ID, 'event': 'late_superseded_offer_delivery',
        'result_kind': 'result_02', 'released_at': 3, 'worker_started_at': started,
        'worker_finished_at': time.time(), 'worker_exit_code': 0,
        'delivered_offer': STALE, 'accepted_current_revision': 2,
        'classification': 'late_and_superseded',
        'native_evidence_sha256': 'f78636454656be994b93cc08f6ffd1cd61cb775314168b4ccde5e59da6e275f2',
    }
    receipt['receipt_sha256'] = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    output = pathlib.Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    print(json.dumps(receipt, sort_keys=True))

if __name__ == '__main__':
    main()
