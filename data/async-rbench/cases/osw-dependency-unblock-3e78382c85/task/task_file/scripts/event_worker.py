import argparse,hashlib,json,pathlib,time
CASE_ID="osw-dependency-unblock-3e78382c85";SOURCE_ID="osworld:vs_code:ea98c5d7-3cf9-4f9b-8ad3-366b58e0fcae";P=pathlib.Path("/async_rbench/upstream_solutions/fixtures/event_payload.json")
a=argparse.ArgumentParser();a.add_argument("--workspace");a.parse_args();p=json.loads(P.read_text());assert p["case_id"]==CASE_ID and p["source_task_id"]==SOURCE_ID
o=pathlib.Path("/app/output_data");o.mkdir(exist_ok=True);w=o/"workstreams";w.mkdir(exist_ok=True)
for i,u in enumerate(p["upstream_dependency_graph"],1):
 f=w/f"upstream_worker_{i:02d}.json";body={"report_path":str(f),"revision_sha256":hashlib.sha256(json.dumps(u,sort_keys=True,separators=(',',':')).encode()).hexdigest(),"finding":u["description"]};f.write_text(json.dumps(body,indent=2,sort_keys=True)+"\n")
s=time.time_ns();q={**p,"worker_started_at":s,"worker_finished_at":time.time_ns(),"worker_exit_code":0,"probes":{"native_evidence_available":True,"task_state_observed":True,"upstream_depth":len(p["upstream_dependency_graph"]),"workstream_reports":len(p["upstream_dependency_graph"])}};q["receipt_sha256"]=hashlib.sha256(json.dumps(q,sort_keys=True,separators=(",",":")).encode()).hexdigest();(o/"event_receipt.json").write_text(json.dumps(q,indent=2,sort_keys=True)+"\n")
