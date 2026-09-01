from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-88206c382b'; SOURCE_ID='bargaining:014'; STALE={"revision": 1, "price": 54.99, "quality_assurance": False, "supply_commitment_months": 0, "status": "superseded"}; CURRENT=2; EVIDENCE_SHA='f78636454656be994b93cc08f6ffd1cd61cb775314168b4ccde5e59da6e275f2'
def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',default='/app/output_data/event_receipt.json'); p.add_argument('--workspace',default='/app'); a=p.parse_args(); started=time.time()
    value={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'late_superseded_offer_delivery','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'delivered_offer':STALE,'accepted_current_revision':CURRENT,'classification':'late_and_superseded','native_evidence_sha256':EVIDENCE_SHA}
    value['receipt_sha256']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); print(json.dumps(value,sort_keys=True))
if __name__=='__main__': main()
