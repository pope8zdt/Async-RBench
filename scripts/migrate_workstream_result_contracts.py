from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

import yaml

from async_rbench.evaluation.report_contract import render_validator_command


@dataclass(frozen=True)
class ValidatorMigration:
    stage: str
    kind: str
    fields: tuple[str, ...] = ()
    must_be_valid_json: bool = False


_EQUALITY_RE = re.compile(
    r"r\s*\[\s*['\"]([^'\"]+)['\"]\s*\]\s*==\s*"
    r"e\s*\[\s*['\"]\1['\"]\s*\]"
)


def classify_validator(command: str) -> ValidatorMigration:
    """Classify only the deterministic report-validator families seen in corpus."""
    compact = " ".join(str(command or "").split())
    evidence_path_fields = {
        field for field in re.findall(
            r"e\s*\[\s*['\"]([^'\"]+_path)['\"]\s*\]", compact,
        )
        if field != "report_path"
    }
    if evidence_path_fields:
        return ValidatorMigration(stage="semantic_evidence", kind="payload_only")
    fields = tuple(dict.fromkeys(_EQUALITY_RE.findall(compact)))
    has_report_path = bool(re.search(r"e\s*\[\s*['\"]report_path['\"]\s*\]", compact))
    has_file_check = bool(re.search(
        r"\.is_file\(\)|os\.path\.(?:isfile|exists)\(|pathlib\.Path\(", compact,
    ))
    has_report_json_load = bool(re.search(r"json\.load\s*\(", compact))
    if has_report_path and has_file_check and fields and has_report_json_load:
        return ValidatorMigration(
            stage="submission_contract",
            kind="report_file",
            fields=fields,
            must_be_valid_json=True,
        )
    assert_count = len(re.findall(r"\bassert\b", compact))
    if has_report_path and has_file_check and not has_report_json_load and assert_count <= 1:
        return ValidatorMigration(
            stage="submission_contract",
            kind="report_file",
            fields=(),
            must_be_valid_json=False,
        )
    return ValidatorMigration(stage="semantic_evidence", kind="payload_only")


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: contract must be an object")
    return value


def _dump(path: Path, value: dict[str, Any]) -> str:
    original = path.read_text(encoding="utf-8")
    if original.lstrip().startswith("{"):
        return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return yaml.safe_dump(
        value, allow_unicode=True, sort_keys=False, width=1000,
    )


def _report_contract(
    path: str, fields: tuple[str, ...], *, must_be_valid_json: bool,
) -> dict[str, Any]:
    return {
        "kind": "report_file",
        "report_file": {
            "path": path,
            "must_exist": True,
            "must_be_valid_json": must_be_valid_json,
            "fields_equal_evidence": list(fields),
        },
    }


def migrate_corpus(root: Path, *, apply: bool) -> dict[str, Any]:
    root = Path(root)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    changes_required = 0
    category_counts = {
        "report_json_equality": 0,
        "report_exists": 0,
        "semantic_evidence": 0,
        "already_migrated": 0,
    }
    public_paths = sorted((root / "cases").rglob("public_case.yaml"))
    workstream_count = 0
    for public_path in public_paths:
        private_path = public_path.parent / "private" / "private_case.yaml"
        if not private_path.is_file():
            errors.append(f"{public_path}: missing private/private_case.yaml")
            continue
        try:
            public = _load(public_path)
            private = _load(private_path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(str(exc))
            continue
        public_changed = False
        private_changed = False
        bindings = private.get("workstream_bindings")
        if not isinstance(bindings, dict):
            errors.append(f"{private_path}: workstream_bindings must be an object")
            continue
        for workstream in public.get("workstreams") or []:
            workstream_count += 1
            if not isinstance(workstream, dict):
                errors.append(f"{public_path}: non-object workstream")
                continue
            stream_id = str(workstream.get("id") or "")
            binding = bindings.get(stream_id)
            if not stream_id or not isinstance(binding, dict):
                errors.append(f"{public_path}: unresolved private binding for {stream_id!r}")
                continue
            command = str(binding.get("validator_command") or "")
            required_files = [str(item) for item in workstream.get("required_files") or []]
            required_evidence = {
                str(item) for item in workstream.get("required_evidence_fields") or []
            }
            current_public = dict(workstream.get("public_result_contract") or {})
            current_report = dict(current_public.get("report_file") or {})
            already_rendered = bool(
                binding.get("validator_stage") == "submission_contract"
                and current_public.get("kind") == "report_file"
                and len(required_files) == 1
                and command == render_validator_command(current_public, required_files[0])
            )
            if already_rendered:
                migration = ValidatorMigration(
                    stage="submission_contract",
                    kind="report_file",
                    fields=tuple(current_report.get("fields_equal_evidence") or []),
                    must_be_valid_json=bool(current_report.get("must_be_valid_json", True)),
                )
            else:
                migration = classify_validator(command)
            if migration.stage == "submission_contract":
                if len(required_files) != 1:
                    errors.append(
                        f"{public_path}: {stream_id}: report validator requires exactly one required file"
                    )
                    continue
                if "report_path" not in required_evidence:
                    errors.append(
                        f"{public_path}: {stream_id}: report validator requires report_path evidence"
                    )
                    continue
                unknown_fields = sorted(set(migration.fields) - required_evidence)
                if unknown_fields:
                    errors.append(
                        f"{public_path}: {stream_id}: validator fields are not public evidence: {unknown_fields!r}"
                    )
                    continue
                desired_public = _report_contract(
                    required_files[0], migration.fields,
                    must_be_valid_json=migration.must_be_valid_json,
                )
                desired_command = render_validator_command(desired_public, required_files[0])
                category = (
                    "report_json_equality" if migration.must_be_valid_json else "report_exists"
                )
            else:
                existing_public = dict(workstream.get("public_result_contract") or {})
                desired_public = {**existing_public, "kind": "payload_only"}
                desired_command = command
                category = "semantic_evidence"
            category_counts[category] += 1
            changed = False
            if workstream.get("public_result_contract") != desired_public:
                workstream["public_result_contract"] = desired_public
                public_changed = changed = True
            if binding.get("validator_stage") != migration.stage:
                binding["validator_stage"] = migration.stage
                private_changed = changed = True
            if str(binding.get("validator_command") or "") != desired_command:
                binding["validator_command"] = desired_command
                private_changed = changed = True
            if changed:
                changes_required += 1
            else:
                category_counts["already_migrated"] += 1
            rows.append({
                "case_id": str(public.get("case_id") or public_path.parent.name),
                "workstream_id": stream_id,
                "public_path": str(public_path.relative_to(root)),
                "classification": asdict(migration),
                "changed": changed,
            })
        if apply and public_changed:
            public_path.write_text(_dump(public_path, public), encoding="utf-8")
        if apply and private_changed:
            private_path.write_text(_dump(private_path, private), encoding="utf-8")
    registry_path = root / "cases" / "registry.json"
    authored_case_count = len(public_paths)
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            authored_case_count = len(registry.get("case_families") or [])
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "authored_case_count": authored_case_count,
        "instantiated_case_count": len(public_paths),
        "instantiated_workstream_count": workstream_count,
        "changes_required": changes_required,
        "errors": errors,
        **category_counts,
        "workstreams": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = migrate_corpus(args.root.resolve(), apply=args.apply)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if report["errors"]:
        return 1
    if args.check and report["changes_required"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
