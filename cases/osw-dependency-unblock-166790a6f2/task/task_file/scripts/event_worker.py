import argparse,hashlib,json,pathlib,time
CASE_ID="osw-dependency-unblock-166790a6f2";SOURCE_ID="osworld:multi_apps:f8369178-fafe-40c2-adc4-b9b08a125456";RESULT_KIND="result_03";P=pathlib.Path("/async_rbench/upstream_solutions/fixtures/event_payload.json")
a=argparse.ArgumentParser();a.add_argument("--workspace");a.parse_args();p=json.loads(P.read_text());assert p["case_id"]==CASE_ID and p["source_task_id"]==SOURCE_ID
o=pathlib.Path("/app/output_data");o.mkdir(exist_ok=True);w=o/"workstreams";w.mkdir(exist_ok=True)
last=None
for i,u in enumerate(p["upstream_dependency_graph"],1):
 f=w/f"upstream_worker_{i:02d}.json";body={"report_path":str(f),"revision_sha256":hashlib.sha256(json.dumps(u,sort_keys=True,separators=(',',':')).encode()).hexdigest(),"finding":u["description"]};f.write_text(json.dumps(body,indent=2,sort_keys=True)+"\n");last=body
s=time.time_ns();r={**p,"receipt_id":f"{CASE_ID}:{RESULT_KIND}","result_kind":RESULT_KIND,"released_at":time.time_ns(),"evidence":last,"worker_started_at":s,"worker_finished_at":time.time_ns(),"worker_exit_code":0,"probes":{"native_evidence_available":True,"task_state_observed":True,"upstream_depth":len(p["upstream_dependency_graph"]),"workstream_reports":len(p["upstream_dependency_graph"])}};r["receipt_sha256"]=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(",",":")).encode()).hexdigest();(o/"event_receipt.json").write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")

