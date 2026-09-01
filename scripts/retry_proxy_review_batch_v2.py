"""Recover one incomplete proxy-review batch by splitting it into smaller calls."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.expansion_v2 import read_jsonl  # noqa: E402
from scripts.run_codex_proxy_review_v2 import LENSES, _run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviewer", choices=sorted(LENSES), required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--original-batch-size", type=int, default=25)
    parser.add_argument("--split-size", type=int, default=5)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--schema", default=str(ROOT / "schemas" / "codex_fixed_choice_review_v2.schema.json"))
    args = parser.parse_args()

    rows = read_jsonl(Path(args.input).resolve())
    start = (args.batch_index - 1) * args.original_batch_size
    target = rows[start : start + args.original_batch_size]
    if not target:
        raise ValueError("requested batch is outside the input")
    chunks = [target[index : index + args.split_size] for index in range(0, len(target), args.split_size)]
    output = Path(args.output).resolve()
    retry_root = output / "retries" / f"{args.reviewer}-batch-{args.batch_index:04d}"
    results = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                _run,
                args.reviewer,
                90000 + index,
                chunk,
                retry_root,
                Path(args.schema).resolve(),
                args.model,
                args.effort,
            ): index
            for index, chunk in enumerate(chunks, 1)
        }
        for future in as_completed(futures):
            _, _, reviews, state = future.result()
            index = futures[future]
            results[index] = reviews
            print(f"retry part {index}/{len(chunks)} {state}", flush=True)
    combined = [review for index in sorted(results) for review in results[index]]
    expected = [str(row["candidate_id"]) for row in target]
    received = [str(row.get("candidate_id")) for row in combined]
    if received != expected:
        raise RuntimeError(f"combined retry id mismatch: expected {expected}, received {received}")
    final_path = output / args.reviewer / f"batch-{args.batch_index:04d}.result.json"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(
        json.dumps({"reviews": combined}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "recovered", "reviewer": args.reviewer, "batch": args.batch_index, "review_count": len(combined)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
