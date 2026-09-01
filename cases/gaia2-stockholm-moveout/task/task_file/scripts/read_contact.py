#!/usr/bin/env python3
"""Public helper: read the Contacts app state.

Prints the contacts JSON to stdout. The record for the friend who is moving to
Stockholm carries the rent budget the friend can spend; it is derived from the
saved-search upper bound in the RentAFlat app (documented transformation, see
PROVENANCE.md).

Usage:
  python3 scripts/read_contact.py
  python3 scripts/read_contact.py --app /app/task_file/app
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_APP = HERE.parent / "app"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the Contacts app state")
    parser.add_argument("--app", default=str(DEFAULT_APP))
    args = parser.parse_args()
    path = Path(args.app) / "contacts.json"
    print(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
