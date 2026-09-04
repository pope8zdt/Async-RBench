"""Per-model batch driver for run_case.ps1.

Run one model's batch across registered instances. Multiple invocations can use
the same bounded instance set, while lanes stride that set without overlap.

Secrets are never written here or to disk: the model's api_key_env value is
read from the process environment (set by the launching shell) and passed to
the run_case.ps1 child via the environment only.

Stop: create the stop flag file (path printed at startup) or send SIGINT;
workers finish their current instance then stop pulling.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POWERSHELL = "powershell.exe"
RUN_CASE = REPO / "run_case.ps1"

def load_instances() -> list[str]:
    reg = json.loads((REPO / "cases" / "registry.json").read_text(encoding="utf-8"))
    insts: list[str] = []
    for ent in reg["case_families"]:
        case_id = ent["case_id"]
        for inst in ent.get("instances", []):
            insts.append(f"{case_id}::{inst['instance_id']}")
    return insts


def sanitize(inst: str) -> str:
    return inst.replace("::", "__").replace("/", "_").replace("\\", "_")


def run_one(inst: str, lane: dict, seq: int, out_dir: Path) -> dict:
    env_key = lane["env_key"]
    key_val = os.environ.get(env_key)
    if not key_val:
        return {"instance": inst, "lane": lane["name"], "started": time.strftime("%H:%M:%S"),
                "exit": "NO-KEY", "detail": f"{env_key} not set in environment"}
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    exp_root = out_dir / f"batch-{lane['name']}-{sanitize(inst)}-{ts}-{seq}"
    exp_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUN_CASE),
        "-Instance", inst,
        "-Config", str(REPO / lane["profile"]),
        "-Repetitions", str(lane["repeat"]),
        "-ExperimentRoot", str(exp_root),
    ]
    env = dict(os.environ)
    env[env_key] = key_val
    start = time.time()
    try:
        # Lane output is UTF-8 (PowerShell + case JSON); the locale default
        # (GBK on this host) raises UnicodeDecodeError and kills the reader
        # thread.  The output is only diagnostic — decode leniently.
        proc = subprocess.run(cmd, cwd=str(REPO), env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=2 * 60 * 60)
        exit_code = proc.returncode
        detail = ""
        # Parse the aggregated result.
        res_path = exp_root / "results.json"
        if res_path.exists():
            try:
                rows = json.loads(res_path.read_text(encoding="utf-8"))["rows"]
                scored = sum(r.get("scored_n", 0) for r in rows)
                unscored = sum(r.get("unscored_n", 0) for r in rows)
                reasons = sorted({r.get("reason", "") for r in rows if r.get("unscored_n", 0)})
                detail = f"scored={scored} unscored={unscored} reasons={reasons}"
            except Exception as e:  # noqa: BLE001
                detail = f"results parse error: {e}"
        else:
            detail = "no results.json"
    except subprocess.TimeoutExpired:
        exit_code = "TIMEOUT"
        detail = "exceeded 2h"
    elapsed = round(time.time() - start, 1)
    return {"instance": inst, "lane": lane["name"], "started": time.strftime("%H:%M:%S"),
            "duration_s": elapsed, "exit": exit_code, "detail": detail,
            "exp_root": str(exp_root)}


def worker(lane: dict, jobs: queue.Queue, out_dir: Path, results: list, lock: threading.Lock,
           stop_flag: Path, done: dict):
    seq = 0
    while True:
        if stop_flag.exists():
            break
        try:
            inst = jobs.get_nowait()
        except queue.Empty:
            break
        if stop_flag.exists():
            jobs.put(inst)
            break
        res = run_one(inst, lane, seq, out_dir)
        seq += 1
        with lock:
            results.append(res)
            done[lane["name"]] += 1
            print(f"[{res['started']}] {lane['name']} #{seq} {res['instance']}: "
                  f"exit={res['exit']} {res['detail']} ({res['duration_s']}s)", flush=True)
        jobs.task_done()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="configs/model-profiles/deepseek-v4-flash-vibecodex.yaml")
    ap.add_argument("--env-key", default="ASYNC_RBENCH_DEEPSEEK_KEY")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--tag", default="model")
    ap.add_argument("--out", default=str(REPO / "artifacts" / "experiments" / "batch-results.jsonl"))
    ap.add_argument("--jobs", type=int, default=0, help="limit instance count (0 = all)")
    ap.add_argument("--lane", type=int, default=0, help="zero-based lane index")
    ap.add_argument("--lanes", type=int, default=1, help="number of lanes striding the instance set")
    ap.add_argument("--stop-flag", default=str(REPO / "batch-stop.FLAG"))
    ap.add_argument("--only-file", default="", help="resume file: one 'case::instance' per line; overrides registry")
    args = ap.parse_args()
    if args.lanes <= 0 or args.lane < 0 or args.lane >= args.lanes:
        ap.error("--lane must satisfy 0 <= lane < lanes and --lanes must be positive")
    lanes = [{
        "name": args.tag,
        "profile": args.profile,
        "env_key": args.env_key,
        "repeat": args.repeat,
    }]

    instances = load_instances()
    if args.only_file:
        path = Path(args.only_file)
        if not path.exists():
            print(f"[batch] FATAL: --only-file {path} not found", flush=True)
            return 1
        instances = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    elif args.jobs and args.jobs > 0:
        instances = instances[: args.jobs]
    instances = instances[args.lane::args.lanes]
    print(f"[batch] {len(instances)} instances, lane {args.lane}/{args.lanes}, "
          f"profile={args.profile}, repeat={args.repeat}", flush=True)
    print(f"[batch] stop flag (write to pause-after-current): {args.stop_flag}", flush=True)

    missing = sorted({l["env_key"] for l in lanes if not os.environ.get(l["env_key"])})
    if missing:
        print(f"[batch] FATAL: missing env keys {missing} — set them before launching.", flush=True)
        return 1

    jobs: queue.Queue = queue.Queue()
    for inst in instances:
        jobs.put(inst)

    out_dir = REPO / "artifacts" / "experiments"
    results: list = []
    done = {l["name"]: 0 for l in lanes}
    lock = threading.Lock()
    stop_flag = Path(args.stop_flag)
    if stop_flag.exists():
        stop_flag.unlink()

    threads = [threading.Thread(target=worker, args=(l, jobs, out_dir, results, lock, stop_flag, done),
                                daemon=True) for l in lanes]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        stop_flag.touch()
        print("[batch] SIGINT: stopped", flush=True)
        for t in threads:
            t.join(timeout=2)
    for t in threads:
        t.join()

    # Persist results.
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    total = len(results)
    scored = sum(1 for r in results if "scored=" in r.get("detail", "") and not r["detail"].startswith("scored=0"))
    print(f"[batch] DONE {total}/{len(instances)} instances written to {out}", flush=True)
    per = {name: done[name] for name in done}
    print(f"[batch] per-lane finished: {per}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
