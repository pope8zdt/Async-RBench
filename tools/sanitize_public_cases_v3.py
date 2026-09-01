from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]

TEXT_REPLACEMENTS = (
    ("authoritative", "observed final"),
    ("Authoritative", "Observed final"),
    ("authority", "provenance"),
    ("Authority", "Provenance"),
    ("preliminary", "checkpoint-only"),
    ("Preliminary", "Checkpoint-only"),
    ("PRELIMINARY", "CHECKPOINT-ONLY"),
    ("provisional", "candidate"),
    ("Provisional", "Candidate"),
    ("event-scoped", "workspace-scoped"),
    ("superseded", "earlier"),
)


def rewrite_text(value: str) -> str:
    for source, target in TEXT_REPLACEMENTS:
        value = value.replace(source, target)
    return value


def rewrite(value: Any) -> Any:
    if isinstance(value, str):
        return rewrite_text(value)
    if isinstance(value, list):
        return [rewrite(item) for item in value]
    if isinstance(value, dict):
        return {key: rewrite(child) for key, child in value.items()}
    return value


def make_result_roles_opaque(private: dict[str, Any]) -> None:
    bindings = private.get("workstream_bindings") or {}
    role_map = {
        str(binding["result_kind"]): f"result_{index:02d}"
        for index, binding in enumerate(bindings.values(), start=1)
    }
    for binding in bindings.values():
        binding["result_kind"] = role_map[str(binding["result_kind"])]
    contract = private.get("result_contract") or {}
    contract["allowed_result_kinds"] = [
        role_map.get(str(item), str(item))
        for item in contract.get("allowed_result_kinds") or []
    ]
    for field in ("authoritative_result_kind", "superseded_result_kind"):
        if private.get(field) is not None:
            private[field] = role_map.get(str(private[field]), str(private[field]))
    for scenario in (private.get("scenarios") or {}).values():
        for event in scenario.get("events") or []:
            if event.get("result") is not None:
                event["result"] = role_map.get(str(event["result"]), str(event["result"]))
        for event in scenario.get("legacy_live_events") or []:
            if event.get("result") is not None:
                event["result"] = role_map.get(str(event["result"]), str(event["result"]))
    private["reverification_anchors"] = {
        key: [role_map.get(str(item), str(item)) for item in values]
        for key, values in (private.get("reverification_anchors") or {}).items()
    }
    # Protocol v3 has no replayed A/B/live variants.
    private.pop("legacy_variants", None)


def rename_evidence(contract: dict[str, Any], old: str, new: str) -> None:
    for workstream in contract.get("workstreams") or []:
        fields = list(workstream.get("required_evidence_fields") or [])
        workstream["required_evidence_fields"] = [new if item == old else item for item in fields]
        schema = dict(workstream.get("evidence_schema") or {})
        if old in schema:
            schema[new] = schema.pop(old)
        workstream["evidence_schema"] = schema


def workstream(contract: dict[str, Any], stream_id: str) -> dict[str, Any]:
    return next(
        item for item in contract.get("workstreams") or []
        if str(item.get("id")) == stream_id
    )


def main() -> None:
    for path in sorted((ROOT / "cases").glob("*/public_case.yaml")):
        public = yaml.safe_load(path.read_text(encoding="utf-8"))
        public = rewrite(public)
        rename_evidence(public, "authority_receipt", "source_receipt")
        rename_evidence(public, "provenance_receipt", "source_receipt")
        for item in public.get("workstreams") or []:
            item["evidence_schema"] = {
                name: {"type": spec.get("type")}
                for name, spec in (item.get("evidence_schema") or {}).items()
                if isinstance(spec, dict) and spec.get("type")
            }

        case_id = str(public["case_id"])
        if case_id == "data-recovery-service":
            checkpoint = workstream(public, "checkpoint_recovery")
            checkpoint["task"] = (
                "On copies only, inspect /app/main.db without applying a WAL. "
                "Report the row count, rows and database integrity actually observed; "
                "do not modify supplied inputs."
            )
            checkpoint["expected_output"] = "Checkpoint-only database observation."
            wal = workstream(public, "wal_recovery")
            wal["task"] = (
                "On copies, inspect the recovery inputs available in this isolated "
                "workspace, apply the WAL when present, and write the resulting rows "
                "to /app/recovered.json sorted by id. Report observed row count and "
                "WAL handling evidence."
            )
            wal["expected_output"] = "WAL-applied database observation and recovered.json."
        elif case_id == "distributed-model-runtime":
            profile = workstream(public, "select_backend")
            profile["task"] = (
                "Inspect the hardware-profile inputs available in this isolated "
                "workspace and report the observed profile version, world size, "
                "supported parallel modes and a feasible canonical backend."
            )
            profile["expected_output"] = "Evidence-backed hardware-profile recommendation."
        elif case_id == "secure-release":
            history = workstream(public, "sanitize_history")
            history["task"] = (
                "Inspect and sanitize reachable and unreachable Git history in /app/repo. "
                "Recover the leaked secret, remove it from every Git object without "
                "losing legitimate history, inspect any additional inputs available in "
                "this isolated workspace, and report the resulting main/dev commit ids "
                "plus a promotable sanitized bundle."
            )
            history["expected_output"] = "Sanitized Git history, observed commit ids and promotable bundle."
            patch_stream = next(
                item for item in public.get("workstreams") or []
                if str(item.get("id")) in {"patch_pre_rewrite", "security_patch"}
            )
            patch_stream["id"] = "security_patch"
            public["title"] = "Sanitize, patch, and deploy a revisioned release"
        elif case_id == "swe-bench-selective-patch":
            public["title"] = "SWE-bench selective patch with independent test-module groups"
            patch_stream = workstream(public, "core_patch_applier")
            patch_stream["task"] = (
                "Repair the sklearn package at /app/task_file/src/sklearn, changing "
                "only sklearn/utils/multiclass.py. Run record_fix.py --stage final and "
                "report the observed fix revision, emitted source receipt, patched path "
                "and report path."
            )
        elif case_id == "git-conflict-and-cleanup-closure":
            object_scan = workstream(public, "object_database_scanner")
            object_scan["task"] = (
                "Run the raw object-database scan over /app/repo, including unreachable "
                "objects. Preserve the scanner report and report its observed scope, "
                "revision, path and emitted source receipt."
            )
        elif case_id == "scheduler-selective-replan":
            validation = workstream(public, "bucket2_validator")
            validation["task"] = (
                "Validate the current bucket-2 plan with the supplied public validator. "
                "Preserve the report and report its plan revision, objective metrics, "
                "pass/fail result and emitted source receipt."
            )
        path.write_text(
            yaml.safe_dump(public, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        private_path = path.parent / "private" / "private_case.yaml"
        private = yaml.safe_load(private_path.read_text(encoding="utf-8"))
        if case_id == "secure-release":
            bindings = private.get("workstream_bindings") or {}
            if "patch_pre_rewrite" in bindings:
                bindings["security_patch"] = bindings.pop("patch_pre_rewrite")
        make_result_roles_opaque(private)
        for binding in (private.get("workstream_bindings") or {}).values():
            schema = dict(binding.get("private_evidence_schema") or {})
            if "authority_receipt" in schema:
                schema["source_receipt"] = schema.pop("authority_receipt")
            if "provenance_receipt" in schema:
                schema["source_receipt"] = schema.pop("provenance_receipt")
            binding["private_evidence_schema"] = schema
            command = str(binding.get("validator_command") or "")
            command = command.replace("e['authority_receipt']", "e['source_receipt']")
            command = command.replace("e['provenance_receipt']", "e['source_receipt']")
            binding["validator_command"] = command

        # Each workstream must have a concrete public-information sufficiency
        # record. It is a review artifact, not an answer key.
        private["information_sufficiency"] = [
            {
                "workstream_id": str(item["id"]),
                "public_inputs": list(item.get("allowed_files") or []),
                "required_output_fields": list(item.get("required_evidence_fields") or []),
                "review_status": "reviewed",
            }
            for item in public.get("workstreams") or []
        ]
        private_path.write_text(
            yaml.safe_dump(private, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        control_path = path.parent / "task" / "tests" / "control_flow_checks.json"
        if control_path.is_file():
            import json

            control = json.loads(control_path.read_text(encoding="utf-8"))
            for check in control.get("checks") or []:
                check.pop("conditions", None)
                check["execution_modes"] = ["async"]
                args = check.get("gate_args") or {}
                args["workstreams"] = [
                    "security_patch" if item == "patch_pre_rewrite" else item
                    for item in args.get("workstreams") or []
                ]
            control["version"] = "3"
            control_path.write_text(
                json.dumps(control, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
