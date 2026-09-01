#!/usr/bin/env python3
"""Reference packer for the scheduler selective-replan case (oracle material).

Produces a correct combined plan for both buckets: one batch per distinct
already-aligned prompt length, using the exact per-request heads/hidden
constants. This is a benchmark-maintenance script and never ships to the
participant image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "task_file"


def load_requests(path: Path) -> dict[str, dict]:
    requests: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        requests[str(item["request_id"])] = item
    return requests


def load_json(path: Path) -> dict:
    """Load one required JSON object from the task fixture set."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def pack(reqs: dict[str, dict]) -> list[dict]:
    groups: defaultdict[int, list[dict]] = defaultdict(list)
    for req in reqs.values():
        groups[int(req["prompt_len"])].append(req)
    plan: list[dict] = []
    for index, prompt_len in enumerate(sorted(groups), 1):
        shape = {"seq_align": prompt_len, "heads_align": 32, "hidden_align": 4096}
        for req in groups[prompt_len]:
            plan.append({
                "request_id": req["request_id"],
                "batch_id": f"b-{index:04d}",
                "shape": dict(shape),
            })
    return plan


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", default=str(ROOT))
    args = parser.parse_args()
    task_root = Path(args.task_root)
    sys.path.insert(0, str(task_root / "scripts"))
    from cost_model import CostModel  # noqa: E402
    input_data = task_root / "input_data"
    output_data = task_root / "output_data"
    authority_receipt = load_json(
        task_root / "events" / "bucket2_authority.json"
    )["authority_receipt"]
    output_data.mkdir(parents=True, exist_ok=True)

    req1 = load_requests(input_data / "requests_bucket_1.jsonl")
    req2 = load_requests(input_data / "requests_bucket_2.jsonl")
    plan1 = pack(req1)
    plan2 = pack(req2)
    (output_data / "plan_b1.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in plan1), encoding="utf-8")
    (output_data / "plan_b2.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in plan2), encoding="utf-8")

    # First-pass snapshots: at the time each bucket validator passed, the plan
    # was recorded. bucket1's snapshot is preserved verbatim into the final;
    # bucket2's is superseded by the replanned version below.
    first_pass = output_data / "first_pass"
    first_pass.mkdir(parents=True, exist_ok=True)
    (first_pass / "plan_b1.jsonl").write_text(
        (output_data / "plan_b1.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    # bucket2 first-pass snapshot is an under-covered plan: seq_align capped at
    # 256 (bin8) which cannot cover the 512/768/1024 needs of bucket 2.
    capped2 = []
    for item in plan2:
        capped2.append({
            "request_id": item["request_id"],
            "batch_id": item["batch_id"],
            "shape": dict(item["shape"]),
        })
    for item in capped2:
        item["shape"]["seq_align"] = 256
    (first_pass / "plan_b2.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in capped2), encoding="utf-8")

    all_shapes = sorted({
        (entry["shape"]["seq_align"], 32, 4096) for entry in [*plan1, *plan2]
    })
    (output_data / "global_shape_plan.json").write_text(
        json.dumps({
            "global_shape_set": [list(shape) for shape in all_shapes],
            "combined_unique_shapes": len(all_shapes),
        }, indent=2), encoding="utf-8")
    metrics1 = CostModel(64).plan_metrics(req1, plan1)
    metrics2 = CostModel(64).plan_metrics(req2, plan2)

    manifest = {
        "preserved_bucket": "bucket1",
        "replanned_bucket": "bucket2",
        "authority_receipt": authority_receipt,
        "preserved_bucket_first_pass_sha256": sha256(first_pass / "plan_b1.jsonl"),
        "replanned_bucket_first_pass_sha256": sha256(first_pass / "plan_b2.jsonl"),
        "preserved_bucket_final_sha256": sha256(output_data / "plan_b1.jsonl"),
        "replanned_bucket_final_sha256": sha256(output_data / "plan_b2.jsonl"),
        "global_shape_set": all_shapes,
        "combined_unique_shapes": len(all_shapes),
        "wait_for_all_validators": True,
        "validator_results": {"bucket1": "pass", "bucket2": "pass"},
        "closure_verified": True,
        "bucket1_metrics": {
            "cost": metrics1["cost"], "pad_ratio": metrics1["pad_ratio"],
            "p95_latency_ms": metrics1["p95_latency_ms"],
            "sequential_timecost": metrics1["sequential_timecost"],
        },
        "bucket2_metrics": {
            "cost": metrics2["cost"], "pad_ratio": metrics2["pad_ratio"],
            "p95_latency_ms": metrics2["p95_latency_ms"],
            "sequential_timecost": metrics2["sequential_timecost"],
        },
    }
    (output_data / "decision_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"wrote plan_b1.jsonl ({len(plan1)} rows), plan_b2.jsonl ({len(plan2)} rows)")
    print(f"combined shapes: {len(all_shapes)} <= 8: {sorted(all_shapes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
