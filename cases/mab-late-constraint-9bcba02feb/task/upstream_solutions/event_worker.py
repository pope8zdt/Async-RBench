from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE='mab-late-constraint-9bcba02feb'; SOURCE='bargaining:009'; STALE={"revision": 1, "price": 24.93, "warranty_months": 0, "quality_evidence": "missing", "status": "superseded"}; CURRENT=2; EVIDENCE='6cbfa25aae32267135484905bbc784206a3e710839e343e34c4dc809e513cd03'
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='/app/output_data/event_receipt.json');p.add_argument('--workspace',default='/app');a=p.parse_args();started=time.time();v={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE,'source_task_id':SOURCE,'event':'late_superseded_offer_delivery','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'delivered_offer':STALE,'accepted_current_revision':CURRENT,'classification':'late_and_superseded','native_evidence_sha256':EVIDENCE};v['receipt_sha256']=hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest();o=pathlib.Path(a.output);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
