#!/usr/bin/env python3
"""Public helper: read the RentAFlat catalog app state.

Prints the catalog JSON to stdout. The catalog is the snapshot of available
listings as of the moment work begins; listings published later arrive through
the event feed (scripts/read_events.py).

Usage:
  python3 scripts/read_catalog.py
  python3 scripts/read_catalog.py --app /app/task_file/app
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_APP = HERE.parent / "app"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the RentAFlat catalog app state")
    parser.add_argument("--app", default=str(DEFAULT_APP))
    args = parser.parse_args()
    path = Path(args.app) / "raf_catalog.json"
    print(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
