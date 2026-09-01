from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, time

CASE_ID = 'mab-cross-app-artifact-496566389d'
SOURCE_ID = 'coding:070'
EVENT = 'quest_sync_contract_delivered'
EVENT_THEME = 'task_scope_or_dependency_change'
MEANING = 'The synchronization worker delivers QuestHub quest and skill-plan record mapping, revision fields, event payloads, idempotency keys, and deterministic concurrent-edit conflict rules.'
AUTHORITY = {'dependency': 'questhub_sync_contract', 'records': ['quest', 'skill_plan'], 'revision_field': 'record_revision', 'idempotency_field': 'event_idempotency_key', 'conflict_policy': 'highest_revision_then_device_id'}
PROBE_PATHS = ["/app/output_data/solution.py"]
COMMAND = None

def digest_path(path):
    p = pathlib.Path(path)
    if not p.exists(): return None
    if p.is_file(): return hashlib.sha256(p.read_bytes()).hexdigest()
    h = hashlib.sha256()
    for child in sorted(x for x in p.rglob("*") if x.is_file() and ".git" not in x.parts):
        h.update(str(child.relative_to(p)).encode()); h.update(b"\0"); h.update(child.read_bytes())
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="/testbed")
    ap.add_argument("--output", default="/app/output_data/event_receipt.json")
    args = ap.parse_args()
    workspace = pathlib.Path(args.workspace)
    before = digest_path(workspace)
    started = time.time(); exit_code = 0; output = ""
    if COMMAND:
        proc = subprocess.run(COMMAND, cwd=workspace, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        exit_code = proc.returncode; output = proc.stdout[-12000:]
    probes = {path: digest_path(path) for path in PROBE_PATHS}
    payload = {
        "schema_version": "async-rbench-event-receipt-v1",
        "case_id": CASE_ID,
        "source_task_id": SOURCE_ID,
        "event": EVENT,
        "event_theme": 'task_scope_or_dependency_change',
        "meaning": MEANING,
        "authority": AUTHORITY,
        "worker_started_at": started,
        "worker_finished_at": time.time(),
        "worker_exit_code": exit_code,
        "worker_output": output,
        "workspace_revision_before": before,
        "workspace_revision_after": digest_path(workspace),
        "probes": probes,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    out = pathlib.Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True)); return exit_code

if __name__ == "__main__": raise SystemExit(main())
