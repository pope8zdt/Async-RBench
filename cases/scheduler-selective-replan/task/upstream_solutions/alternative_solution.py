#!/usr/bin/env python3
"""Independent deterministic constructor for the scheduler equivalence path."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path("/app/task_file")
OUT = ROOT / "output_data"


def read_requests(number: int) -> list[dict]:
    path = ROOT / "input_data" / f"requests_bucket_{number}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def make_plan(requests: list[dict], prefix: str) -> list[dict]:
    by_length: dict[int, list[dict]] = defaultdict(list)
    for request in requests:
        by_length[int(request["prompt_len"])].append(request)
    rows: list[dict] = []
    for sequence, prompt_len in enumerate(sorted(by_length), 1):
        for request in sorted(by_length[prompt_len], key=lambda item: item["request_id"]):
            rows.append({
                "request_id": request["request_id"],
                "batch_id": f"{prefix}-{sequence:03d}",
                "shape": {
                    "seq_align": prompt_len,
                    "heads_align": 32,
                    "hidden_align": 4096,
                },
            })
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    first = OUT / "first_pass"
    first.mkdir(parents=True, exist_ok=True)
    plans = {number: make_plan(read_requests(number), f"alt-b{number}") for number in (1, 2)}
    for number, rows in plans.items():
        write_jsonl(OUT / f"plan_b{number}.jsonl", rows)
    write_jsonl(first / "plan_b1.jsonl", plans[1])
    stale_bucket2 = [
        {**row, "shape": {**row["shape"], "seq_align": 256}}
        for row in plans[2]
    ]
    write_jsonl(first / "plan_b2.jsonl", stale_bucket2)
    shapes = sorted({
        (row["shape"]["seq_align"], row["shape"]["heads_align"], row["shape"]["hidden_align"])
        for rows in plans.values() for row in rows
    })
    (OUT / "global_shape_plan.json").write_text(json.dumps({
        "global_shape_set": [list(shape) for shape in shapes],
        "combined_unique_shapes": len(shapes),
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
