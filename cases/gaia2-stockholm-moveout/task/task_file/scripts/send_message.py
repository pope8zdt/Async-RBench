#!/usr/bin/env python3
"""Public helper: send a Messages-app notification to the friend.

Appends one notification line to the notifications log (the Messages app's
outbox) under the output directory. The log is one JSON object per line. Seq is
assigned deterministically from the log so repeated runs and the reference
solution agree exactly.

Usage:
  python3 scripts/send_message.py --recipient "Linnea Svensson" \
      --listing-id apt-sthlm-vasastan --apartment "Vasastan Serenity" \
      --price 1800 --at 32
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path("/app/output_data")
DEFAULT_LOG = "notifications.jsonl"


def notifications_path(output_root: Path, log_name: str) -> Path:
    return Path(output_root) / log_name


def next_seq(path: Path) -> int:
    if not path.is_file():
        return 1
    seqs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            seqs.append(int(json.loads(line)["seq"]))
    return (max(seqs) + 1) if seqs else 1


def send_notification(
    recipient: str, listing_id: str, apartment: str, price_sek: int, at: int,
    output_root: Path = DEFAULT_OUTPUT, log_name: str = DEFAULT_LOG,
) -> dict:
    path = notifications_path(output_root, log_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "seq": next_seq(path),
        "recipient": recipient,
        "listing_id": listing_id,
        "apartment": apartment,
        "price_sek": int(price_sek),
        "at": int(at),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a Messages-app notification")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--listing-id", required=True)
    parser.add_argument("--apartment", required=True)
    parser.add_argument("--price", type=int, required=True)
    parser.add_argument("--at", type=int, default=0)
    args = parser.parse_args()
    entry = send_notification(
        args.recipient, args.listing_id, args.apartment, args.price, args.at,
        Path(args.output_root), args.log,
    )
    print(json.dumps(entry, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
