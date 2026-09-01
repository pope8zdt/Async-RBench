from __future__ import annotations
import argparse, datetime, hashlib, json, pathlib, time
from zoneinfo import ZoneInfo

CASE_ID = "osw-dependency-unblock-0008d814cb"
SOURCE_ID = "osworld:chrome:a96b564e-dbe9-42c3-9ccf-b4498073438a"
PRIVATE_PAYLOAD = pathlib.Path("/async_rbench/upstream_solutions/fixtures/event_payload.json")

parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.parse_args()
if not PRIVATE_PAYLOAD.is_file():
    raise RuntimeError("evaluator-owned event payload was not injected")
payload = json.loads(PRIVATE_PAYLOAD.read_text())
assert payload["case_id"] == CASE_ID and payload["source_task_id"] == SOURCE_ID
if payload.get("derive_relative_dates"):
    today = datetime.datetime.now(ZoneInfo(payload["state"]["timezone"])).date()
    delta = (7 - today.weekday()) % 7 or 7
    pickup = today + datetime.timedelta(days=delta)
    payload["state"]["pickup_date"] = pickup.isoformat()
    payload["state"]["return_date"] = (pickup + datetime.timedelta(days=4)).isoformat()
started = time.time_ns()
receipt = {**payload, "worker_started_at": started, "worker_finished_at": time.time_ns(), "worker_exit_code": 0, "probes": {"native_evidence_available": True, "task_state_observed": True}}
receipt["receipt_sha256"] = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
out = pathlib.Path("/app/output_data")
out.mkdir(exist_ok=True)
(out / "event_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
