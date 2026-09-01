#!/usr/bin/env python3
"""Record a repo-cleanup attempt in /app/output_data/cleanup_reports/.

The participant performs the actual cleanup with git directly. This script
records the attempt so the closure verifier and the decision manifest can
attribute each verification result to the attempt that produced it.

Usage: record_cleanup.py --attempt <int> --command "<the git command(s) run>"
"""
import argparse
import json
import os
import sys

CLEANUP_DIR = "/app/output_data/cleanup_reports"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()
    os.makedirs(CLEANUP_DIR, exist_ok=True)
    path = os.path.join(CLEANUP_DIR, f"{args.attempt}.json")
    report = {
        "attempt": args.attempt,
        "command": args.command,
        "verified": None,  # filled in by verify_closure.py
        "closed_at_verify": None,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
