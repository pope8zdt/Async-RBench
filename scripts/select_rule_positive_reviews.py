"""Select reviews with at least one rule-screen decision for model adjudication."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    reviews = read_jsonl(Path(args.reviews).resolve())
    labels = read_jsonl(Path(args.labels).resolve())
    positive_ids = {
        str(label.get("review_id") or "")
        for label in labels
        if len(label.get("candidate_decisions") or []) > 0
    }
    selected = [
        review for review in reviews if str(review.get("review_id") or "") in positive_ids
    ]
    output = Path(args.output).resolve()
    write_jsonl(output, selected)
    print(f"selected={len(selected)} rule_positive_ids={len(positive_ids)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
