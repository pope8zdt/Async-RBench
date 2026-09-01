from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION = ROOT / "candidate_cases" / "rebuild-to-100" / "selection-manifest.json"
DEFAULT_BLUEPRINTS = ROOT / "candidate_cases" / "rebuild-to-100" / "blueprints"
DEFAULT_SOURCE = ROOT / "artifacts" / "case-transformability-audit-v2" / "cases.jsonl"
DEFAULT_OUTPUT = ROOT / "candidate_cases" / "rebuild-to-100" / "materialization-audit.json"

REQUIRED_FILES = (
    "instruction.md",
    "task/task.yaml",
    "task/task_file/participant_task.json",
    "task/task_file/async_contract.json",
    "public_case.yaml",
    "private/private_case.yaml",
    "private/case_ir.json",
    "private/score_plan.json",
    "private/dynamic_point_plan.json",
    "private/runtime_contract.json",
    "private/source_lock.json",
    "private/event_policy.json",
    "private/source_adapter.json",
    "private/quality_contract.yaml",
    "mutation_families.json",
    "STATUS.json",
    "PROVENANCE.md",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_rows(path: Path) -> dict[str, dict[str, Any]]:
    return {
        row["case_id"]: row
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    }


def audit(selection_path: Path, blueprints: Path, source_path: Path) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    def fail(check: str, detail: str) -> None:
        errors.append({"check": check, "detail": detail})

    selection = _json(selection_path)
    selected = {item["case_id"]: item for item in selection["cases"]}
    source = _source_rows(source_path)

    manifest_ids: list[str] = []
    manifest_counts: dict[str, int] = {}
    for shard in (1, 2, 3):
        path = blueprints / f"manifest-shard-{shard}.json"
        if not path.is_file():
            fail("shard_manifests", f"missing {path.name}")
            continue
        payload = _json(path)
        ids = [item.get("case_id") for item in payload.get("cases", [])]
        manifest_counts[str(shard)] = len(ids)
        manifest_ids.extend(ids)
        if payload.get("shard") != shard or payload.get("case_count") != len(ids):
            fail("shard_manifests", f"{path.name} metadata/count mismatch")
        expected = {case_id for case_id, item in selected.items() if item.get("shard") == shard}
        if set(ids) != expected or len(ids) != len(set(ids)):
            fail("shard_manifests", f"{path.name} cases differ from selection shard")

    if len(manifest_ids) != 82 or Counter(manifest_ids) != Counter(selected.keys()):
        fail("manifest_selection_exact", "three manifests must contain exactly the 82 selected cases once")

    directory_ids = {p.name for p in blueprints.iterdir() if p.is_dir()} if blueprints.is_dir() else set()
    if directory_ids != set(selected):
        fail("directory_selection_exact", "blueprint directories differ from selection")

    theme_policies: dict[str, dict[str, Any]] = {}
    theme_counts: Counter[str] = Counter()
    audited = 0
    for case_id in sorted(selected):
        case_dir = blueprints / case_id
        if case_id not in source:
            fail("source_binding", f"{case_id}: absent from source blueprint audit")
            continue
        missing = [name for name in REQUIRED_FILES if not (case_dir / name).is_file()]
        if missing:
            fail("required_files", f"{case_id}: missing {', '.join(missing)}")
            continue
        audited += 1
        row = source[case_id]
        case_ir = _json(case_dir / "private/case_ir.json")
        score = _json(case_dir / "private/score_plan.json")
        if case_ir != row["case_ir_blueprint"]:
            fail("case_ir_exact", f"{case_id}: case_ir differs from source blueprint")
        if score.get("semantic_points") != row["semantic_score_blueprint"]:
            fail("semantic_exact", f"{case_id}: semantic points differ from source blueprint")
        if score.get("control_points") != row["control_score_blueprint"]:
            fail("control_exact", f"{case_id}: control points differ from source blueprint")

        policy = _json(case_dir / "private/event_policy.json")
        private_case = _json(case_dir / "private/private_case.yaml")
        theme = row["async_classification_plan"]["primary_event_theme"]
        theme_counts[theme] += 1
        if policy.get("theme") != theme or private_case.get("classification", {}).get("primary_event_theme") != theme:
            fail("event_policy", f"{case_id}: event theme binding mismatch")
        if policy.get("event_contract") != row["case_ir_blueprint"]["event_contract"]:
            fail("event_policy", f"{case_id}: event contract differs from source blueprint")
        comparable = {k: v for k, v in policy.items() if k not in {"event_id", "event_contract"}}
        if theme in theme_policies and theme_policies[theme] != comparable:
            fail("event_policy", f"{case_id}: policy fields inconsistent within theme {theme}")
        theme_policies.setdefault(theme, comparable)

        for path in (case_dir / "task").rglob("*"):
            if path.is_file() and "source_manifests" in path.parts:
                fail("private_source_isolation", f"{case_id}: source manifest leaked into task tree")
        adapter = _json(case_dir / "private/source_adapter.json")
        for entry in adapter.get("private_source_manifests", []):
            private_copy = str(entry.get("private_copy", "")).replace("\\", "/")
            if not private_copy.startswith("private/source_manifests/") or not (case_dir / private_copy).is_file():
                fail("private_source_isolation", f"{case_id}: invalid private source-manifest binding")

        status = _json(case_dir / "STATUS.json")
        for key in ("registered", "runtime_executed", "quality_execution_passed"):
            if status.get(key) is not False:
                fail("status_claims", f"{case_id}: {key} must be false")
        status_text = str(status.get("status", "")).lower()
        if not status_text or any(word in status_text for word in ("registered", "runtime_passed", "quality_passed")):
            fail("status_claims", f"{case_id}: status text makes an unsupported claim")

    expected_themes = set(selection.get("final_theme_counts", selection.get("theme_counts", {})))
    if len(theme_counts) != 8 or (expected_themes and set(theme_counts) != expected_themes):
        fail("eight_event_policies", f"expected 8 selected event themes, found {len(theme_counts)}")

    return {
        "schema_version": "async-rbench-materialization-audit-v1",
        "passed": not errors,
        "selected_case_count": len(selected),
        "manifest_case_count": len(manifest_ids),
        "audited_case_count": audited,
        "manifest_shard_counts": manifest_counts,
        "event_theme_counts": dict(sorted(theme_counts.items())),
        "checks": {
            "manifest_selection_exact": not any(e["check"] in {"shard_manifests", "manifest_selection_exact"} for e in errors),
            "directory_selection_exact": not any(e["check"] == "directory_selection_exact" for e in errors),
            "required_files_complete": not any(e["check"] == "required_files" for e in errors),
            "private_source_isolation": not any(e["check"] == "private_source_isolation" for e in errors),
            "event_policies_consistent": not any(e["check"] in {"event_policy", "eight_event_policies"} for e in errors),
            "source_blueprints_exact": not any(e["check"] in {"case_ir_exact", "semantic_exact", "control_exact"} for e in errors),
            "status_claims_conservative": not any(e["check"] == "status_claims" for e in errors),
        },
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the 82 materialized Async-RBench blueprints.")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--blueprints", type=Path, default=DEFAULT_BLUEPRINTS)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = audit(args.selection, args.blueprints, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
