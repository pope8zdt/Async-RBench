#!/usr/bin/env python3
"""Deterministic validator for the scheduler selective-replan case.

This script is PUBLIC task material: the participant runs it to check a plan,
and the private verifier reuses it to score the final submitted plans. It has
no knowledge of which bucket "should" be preserved or replanned; it reports
facts about the submitted plan files against the request files and the shared
shape budget.

Usage:
  python validate_plan.py \
      --requests-bucket1 input_data/requests_bucket_1.jsonl \
      --requests-bucket2 input_data/requests_bucket_2.jsonl \
      --plan-b1 output_data/plan_b1.jsonl \
      --plan-b2 output_data/plan_b2.jsonl \
      --shape-budget 8 \
      --out report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cost_model import CostModel, align  # noqa: E402

# Derived from the case's engineered fixtures with a safety margin over the
# reference packer (see PROVENANCE.md). The thresholds are public; a plan that
# pads every request into one oversized shape fails them.
THRESHOLDS = {
    "bucket1": {"cost": 1.5e9, "pad_ratio": 0.045, "p95_ms": 2.0e5, "seq_ms": 5.0e5},
    "bucket2": {"cost": 1.0e10, "pad_ratio": 0.040, "p95_ms": 8.0e5, "seq_ms": 2.0e6},
}


def load_requests(path: Path) -> dict[str, dict]:
    requests: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        requests[str(item["request_id"])] = item
    return requests


def load_plan(path: Path) -> tuple[list[dict], dict[str, dict]]:
    plan = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        plan.append(json.loads(line))
    by_batch: dict[str, dict] = {}
    for entry in plan:
        shape = entry.get("shape") or {}
        by_batch[str(entry["batch_id"])] = {
            "seq_align": int(shape.get("seq_align", 0)),
            "heads_align": int(shape.get("heads_align", 0)),
            "hidden_align": int(shape.get("hidden_align", 0)),
        }
    return plan, by_batch


def validate_bucket(
    requests: dict[str, dict], plan: list[dict],
    by_batch: dict[str, dict], budget: int, name: str,
) -> dict:
    issues: list[str] = []
    plan_ids = [str(entry.get("request_id")) for entry in plan]
    if len(plan_ids) != len(set(plan_ids)):
        issues.append("duplicate request_id in plan")
    if set(plan_ids) != set(requests):
        missing = sorted(set(requests) - set(plan_ids))
        extra = sorted(set(plan_ids) - set(requests))
        issues.append(f"plan request set mismatch: missing={missing} extra={extra}")
    shapes: set[tuple[int, int, int]] = set()
    for entry in plan:
        shape = entry.get("shape") or {}
        seq = int(shape.get("seq_align", 0))
        heads = int(shape.get("heads_align", 0))
        hidden = int(shape.get("hidden_align", 0))
        req = requests.get(str(entry.get("request_id")))
        if req is None:
            continue
        need = align(int(req["prompt_len"]), 64)
        if seq % 64 != 0 or seq < need:
            issues.append(f"{entry.get('request_id')}: seq_align {seq} does not cover need {need}")
        if heads != 32:
            issues.append(f"{entry.get('request_id')}: heads_align must be 32")
        if hidden != 4096:
            issues.append(f"{entry.get('request_id')}: hidden_align must be 4096")
        shapes.add((seq, heads, hidden))
    if len(shapes) > budget:
        issues.append(f"unique shapes {len(shapes)} exceed shared budget {budget}")
    metrics = CostModel(64).plan_metrics(requests, plan)
    thr = THRESHOLDS[name]
    if metrics["cost"] > thr["cost"]:
        issues.append(f"cost {metrics['cost']:.3e} > {thr['cost']:.3e}")
    if metrics["pad_ratio"] > thr["pad_ratio"]:
        issues.append(f"pad_ratio {metrics['pad_ratio']:.4f} > {thr['pad_ratio']:.4f}")
    if metrics["p95_latency_ms"] > thr["p95_ms"]:
        issues.append(f"p95 {metrics['p95_latency_ms']:.3e} > {thr['p95_ms']:.3e}")
    if metrics["sequential_timecost"] > thr["seq_ms"]:
        issues.append(f"seq_timecost {metrics['sequential_timecost']:.3e} > {thr['seq_ms']:.3e}")
    return {
        "bucket": name,
        "passes": not issues,
        "issues": issues,
        "metrics": {
            "cost": metrics["cost"], "pad_ratio": metrics["pad_ratio"],
            "p95_latency_ms": metrics["p95_latency_ms"],
            "sequential_timecost": metrics["sequential_timecost"],
            "unique_shapes": len(shapes),
            "shape_set": sorted(shapes),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests-bucket1", required=True)
    parser.add_argument("--requests-bucket2", required=True)
    parser.add_argument("--plan-b1", required=True)
    parser.add_argument("--plan-b2", required=True)
    parser.add_argument("--shape-budget", type=int, default=8)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    req1 = load_requests(Path(args.requests_bucket1))
    req2 = load_requests(Path(args.requests_bucket2))
    plan1, batch1 = load_plan(Path(args.plan_b1))
    plan2, batch2 = load_plan(Path(args.plan_b2))
    all_shapes = (
        set(
            (shape["seq_align"], shape["heads_align"], shape["hidden_align"])
            for shape in batch1.values()
        )
        | set(
            (shape["seq_align"], shape["heads_align"], shape["hidden_align"])
            for shape in batch2.values()
        )
    )
    results = [
        validate_bucket(req1, plan1, batch1, args.shape_budget, "bucket1"),
        validate_bucket(req2, plan2, batch2, args.shape_budget, "bucket2"),
    ]
    for item, plan_path in zip(results, (Path(args.plan_b1), Path(args.plan_b2))):
        item["plan_revision"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    authority_path = HERE.parent / "events" / "bucket2_authority.json"
    if authority_path.is_file():
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        results[1]["authority_receipt"] = authority["authority_receipt"]
    report = {
        "valid": all(item["passes"] for item in results),
        "results": results,
        "combined_unique_shapes": len(all_shapes),
        "combined_shape_set": sorted(all_shapes),
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
