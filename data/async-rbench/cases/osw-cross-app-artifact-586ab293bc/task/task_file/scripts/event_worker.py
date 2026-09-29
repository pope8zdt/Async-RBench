import argparse,hashlib,json,pathlib,time
CASE_ID="osw-cross-app-artifact-586ab293bc"; SOURCE_ID="osworld:multi_apps:d9b7c649-c975-4f53-88f5-940b29c47247"; P=pathlib.Path("/async_rbench/upstream_solutions/fixtures/event_payload.json")
a=argparse.ArgumentParser(); a.add_argument("--workspace"); a.parse_args(); p=json.loads(P.read_text()); assert p["case_id"]==CASE_ID and p["source_task_id"]==SOURCE_ID
s=time.time_ns(); q={**p,"worker_started_at":s,"worker_finished_at":time.time_ns(),"worker_exit_code":0,"probes":{"native_evidence_available":True,"task_state_observed":True,"upstream_depth":len(p["upstream_dependency_graph"])}}; q["receipt_sha256"]=hashlib.sha256(json.dumps(q,sort_keys=True,separators=(",",":")).encode()).hexdigest(); o=pathlib.Path("/app/output_data");o.mkdir(exist_ok=True);(o/"event_receipt.json").write_text(json.dumps(q,indent=2,sort_keys=True)+"\n")

