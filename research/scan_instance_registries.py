"""Scan every registered instance's semantic_checks.json against validate_scoring_domains.

Run: python research/scan_instance_registries.py
Exit 0 if all pass; otherwise prints the failing instance keys.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from async_rbench.spec import discover_case_instances
from async_rbench.evaluation.case_contract import validate_scoring_domains


def registry_for(instance) -> Path:
    return Path(instance.case_dir) / "task" / "tests" / "semantic_checks.json"


def main() -> int:
    from async_rbench.spec import discover_cases
    case_ids = [c.case_id for c in discover_cases(ROOT)]
    instances = discover_case_instances(ROOT, case_ids)
    total = len(instances)
    passing = 0
    failing = []
    for inst in instances:
        path = registry_for(inst)
        if not path.is_file():
            failing.append((inst.case_id, inst.instance_id, "missing registry"))
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failing.append((inst.case_id, inst.instance_id, f"unreadable: {exc}"))
            continue
        errors = validate_scoring_domains(list(data.get("checks") or []))
        if errors:
            failing.append((inst.case_id, inst.instance_id, f"{len(errors)} domain errors"))
        else:
            passing += 1
    print(f"total instances: {total}, passing: {passing}, failing: {len(failing)}")
    for case_id, instance_id, why in failing:
        print(f"  FAIL {case_id}::{instance_id} -- {why}")
    # case-level summary: which cases would pass a case-level conformance gate
    # (run_conformance exercises EVERY registered instance of a case).
    by_case: dict[str, list[str]] = {}
    for inst in instances:
        by_case.setdefault(inst.case_id, []).append(inst.instance_id)
    bad_cases = {c for c, iid, _ in failing}
    print("\ncase-level summary (instances per case; case-level conformance-safe if none fail):")
    for case_id in sorted(by_case):
        flag = "OK " if case_id not in bad_cases else "BAD"
        print(f"  [{flag}] {case_id}: {by_case[case_id]}")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
