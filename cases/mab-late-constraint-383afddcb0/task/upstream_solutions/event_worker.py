from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-late-constraint-383afddcb0'; SOURCE_ID='research:051'; EVIDENCE_SHA='5d2bb6319923a931be0f9eeef35a1e253f6611526e0370942c419dae7572e6a9'
AUTHORITY={'title':'TopoScan-Mamba: pruning-aware continuous 2D state-space vision','method':'resolution-flexible continuous 2D scanning with pruning-aware hidden-state alignment and token-importance calibration','anchors':["PlainMamba", "continuous 2D scanning", "spatial adjacency", "token-dependent B C and Delta"],'datasets':["ImageNet-1K", "ADE20K", "COCO"],'metrics':["top-1 accuracy", "mIoU", "AP", "FLOPs", "latency", "scan-discontinuity rate"]}
def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',default='/app/output_data/event_receipt.json'); p.add_argument('--workspace',default='/app'); a=p.parse_args(); started=time.time()
    value={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'delayed_authoritative_research_result','result_kind':'result_02','released_at':3,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'authority':AUTHORITY,'native_evidence_sha256':EVIDENCE_SHA}
    value['receipt_sha256']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); print(json.dumps(value,sort_keys=True))
if __name__=='__main__': main()
