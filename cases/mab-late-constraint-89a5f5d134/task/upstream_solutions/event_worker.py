from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE='mab-late-constraint-89a5f5d134'; SOURCE='bargaining:015'; STALE={"revision": 1, "price": 11.99, "compatibility": "unverified", "bundled_logistics": False, "status": "superseded"}; CURRENT=2; EVIDENCE='aa80cc353bca6a8aeba33935ab585e7da8eb2c0da1e349f643626fd212eb092c'
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='/app/output_data/event_receipt.json');p.add_argument('--workspace',default='/app');a=p.parse_args();started=time.time();v={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE,'source_task_id':SOURCE,'event':'late_superseded_offer_delivery','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'delivered_offer':STALE,'accepted_current_revision':CURRENT,'classification':'late_and_superseded','native_evidence_sha256':EVIDENCE};v['receipt_sha256']=hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest();o=pathlib.Path(a.output);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
