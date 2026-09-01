from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from async_rbench.strict_case_task_audit import build_strict_case_task_audit, write_audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed publication audit for registered and generated case tasks."
    )
    parser.add_argument(
        "--output",
        default="artifacts/strict-case-task-audit-v1/audit.json",
    )
    args = parser.parse_args()
    audit = build_strict_case_task_audit(ROOT)
    output = ROOT / args.output
    write_audit(audit, output)
    summary = {
        "output": str(output),
        "registered": audit["registered_case_tasks"]["summary"],
        "generated": audit["generated_case_tasks"]["summary"],
        "technically_complete_rebuild_candidates": audit["generated_case_tasks"][
            "technically_complete_rebuild_candidates"
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

