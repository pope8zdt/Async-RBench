from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from async_rbench.case_transformability import (
    build_transformability_audit,
    write_transformability_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/case-transformability-audit-v2")
    args = parser.parse_args()
    audit = build_transformability_audit(ROOT)
    output = (ROOT / args.output).resolve()
    write_transformability_audit(audit, output)
    print(json.dumps({"output": str(output), **audit["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
