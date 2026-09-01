#!/usr/bin/env python3
"""Public helper: read the RentAFlat saved-list app state.

Prints the saved-list JSON to stdout. The list is maintained for a friend who
is moving to Stockholm; the ``search_preferences`` block on the saved list
records the criteria the list is maintained under.

Usage:
  python3 scripts/read_saved_list.py
  python3 scripts/read_saved_list.py --app /app/task_file/app
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_APP = HERE.parent / "app"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the RentAFlat saved-list app state")
    parser.add_argument("--app", default=str(DEFAULT_APP))
    args = parser.parse_args()
    path = Path(args.app) / "raf_saved_list.json"
    print(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
