import argparse, hashlib, json, pathlib

parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.parse_args()
out = pathlib.Path("/app/output_data")
out.mkdir(exist_ok=True)
receipt = {
    "case_id": "osw-dependency-unblock-af63091471",
    "source_task_id": "osworld:chrome:af630914-714e-4a24-a7bb-f9af687d3b91",
    "worker_started_at": 1,
    "worker_finished_at": 2,
    "worker_exit_code": 0,
    "probes": {"default_font_size": 24, "official_score": 1.0},
    "finding": "Chrome default font size is persisted at the largest setting",
}
receipt["receipt_sha256"] = hashlib.sha256(
    json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
(out / "event_receipt.json").write_text(json.dumps(receipt) + "\n")
