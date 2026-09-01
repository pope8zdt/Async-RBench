from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, time

CASE_ID = 'mab-dependency-unblock-71568ae6c9'
SOURCE_ID = 'coding:054'
EVENT = 'validated_map_checkpoint_recovered'
EVENT_THEME = 'task_scope_or_dependency_change'
MEANING = 'The recovered map worker delivers an authoritative fixed-seed checkpoint proving objective placement, destructible terrain, power-ups, and balance invariants, which releases the multiplayer dependency.'
AUTHORITY = {'dependency': 'validated_map_checkpoint', 'map_revision': 'map-r17', 'fixed_seed': 1701, 'validated_invariants': ['objective_placement', 'destructible_terrain', 'power_ups', 'balance'], 'releases': ['matchmaking', 'chat', 'action_sync'], 'stale_action_policy': 'reject_wrong_map_revision'}
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
