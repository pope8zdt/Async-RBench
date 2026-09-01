from __future__ import annotations

import argparse
import json
from pathlib import Path

from async_rbench.cli import _case_promote_prechecks


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases" / "rebuild-batch-001"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "first-10-quality" / "promotion-precheck.json",
    )
    args = parser.parse_args()
    manifest = json.loads((BATCH / "batch-manifest.json").read_text(encoding="utf-8"))
    rows: list[dict] = []
    prefixes: list[str] = []
    for item in manifest["cases"]:
        case_id = str(item["case_id"])
        candidate = BATCH / case_id
        control = json.loads(
            (candidate / "task/tests/control_flow_checks.json").read_text(encoding="utf-8")
        )
        prefix = str(control["checks"][0]["id"]).split(".cf.", 1)[0]
        prefixes.append(prefix)
        _, errors = _case_promote_prechecks(case_id, candidate, prefix)
        rows.append({
            "case_id": case_id,
            "control_prefix": prefix,
            "passed": not errors,
            "errors": errors,
        })
    duplicate_prefixes = sorted({value for value in prefixes if prefixes.count(value) > 1})
    summary = {
        "schema_version": "1",
        "passed": all(row["passed"] for row in rows) and not duplicate_prefixes,
        "technical_prechecks_passed": sum(row["passed"] for row in rows),
        "total": len(rows),
        "duplicate_control_prefixes": duplicate_prefixes,
        "results": rows,
        "registry_mutated": False,
        "note": "Technical dry-run only; explicit human approval is still required for registry promotion.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
