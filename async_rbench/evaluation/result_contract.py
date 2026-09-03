from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import re
import shlex
from typing import Any

from .report_contract import classify_validator_output
from .workspace_runtime import WorkspaceRuntime


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


@dataclass(frozen=True)
class ResultContractValidation:
    """Evaluator-owned validation result for one hidden child completion."""

    valid: bool
    reason_codes: tuple[str, ...]
    details: tuple[str, ...]
    validator_exit_code: int | None = None
    validator_output: str = ""

    def private_event_fields(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason_codes": list(self.reason_codes),
            "details": list(self.details),
            "validator_exit_code": self.validator_exit_code,
            "validator_output": self.validator_output,
        }


def _is_json_type(value: Any, expected: str) -> bool:
    types = _JSON_TYPES[expected]
    if expected in {"integer", "number"} and isinstance(value, bool):
        return False
    return isinstance(value, types)


def _append_failure(
    codes: list[str], details: list[str], code: str, detail: str,
) -> None:
    if code not in codes:
        codes.append(code)
    details.append(detail)


def validate_payload_contract(
    workstream: dict[str, Any], event: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Validate the declarative, transport-level portion of a result contract."""

    codes: list[str] = []
    details: list[str] = []
    payload = event.get("payload")
    if not isinstance(payload, dict):
        _append_failure(codes, details, "payload_not_object", "payload must be an object")
        return codes, details

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        _append_failure(codes, details, "evidence_not_object", "payload.evidence must be an object")
        evidence = {}

    required_fields = list(workstream.get("required_evidence_fields") or [])
    missing_fields = [
        str(name) for name in required_fields
        if evidence.get(str(name)) is None or evidence.get(str(name)) == ""
    ]
    if missing_fields:
        _append_failure(
            codes, details, "missing_required_evidence",
            "missing evidence fields: " + ", ".join(missing_fields),
        )

    evidence_schema = dict(workstream.get("evidence_schema") or {})
    for field_name, field_spec in evidence_schema.items():
        if field_name not in evidence:
            continue
        value = evidence[field_name]
        field_spec = dict(field_spec or {})
        expected_type = field_spec.get("type")
        if expected_type and not _is_json_type(value, str(expected_type)):
            _append_failure(
                codes, details, "evidence_constraint_failed",
                f"evidence.{field_name} must have type {expected_type}",
            )
            continue
        if "const" in field_spec and value != field_spec["const"]:
            _append_failure(
                codes, details, "evidence_constraint_failed",
                f"evidence.{field_name} does not equal its evaluator-owned constant",
            )
        if "enum" in field_spec and value not in list(field_spec["enum"]):
            _append_failure(
                codes, details, "evidence_constraint_failed",
                f"evidence.{field_name} is outside its evaluator-owned enum",
            )
        if "pattern" in field_spec and (
            not isinstance(value, str) or re.fullmatch(str(field_spec["pattern"]), value) is None
        ):
            _append_failure(
                codes, details, "evidence_constraint_failed",
                f"evidence.{field_name} does not match its evaluator-owned pattern",
            )
        if isinstance(value, (list, dict, str)) and "min_items" in field_spec:
            if len(value) < int(field_spec["min_items"]):
                _append_failure(
                    codes, details, "evidence_constraint_failed",
                    f"evidence.{field_name} has fewer than {field_spec['min_items']} items",
                )

    files = payload.get("files")
    if not isinstance(files, list) or any(not isinstance(path, str) or not path for path in files):
        _append_failure(
            codes, details, "files_not_string_list",
            "payload.files must be a list of non-empty paths",
        )
        files = []
    if len(files) != len(set(files)):
        _append_failure(codes, details, "duplicate_files", "payload.files contains duplicate paths")

    allowed_files = set(str(path) for path in workstream.get("allowed_files") or [])
    required_list = [str(path) for path in workstream.get("required_files") or []]
    required_files = set(required_list)
    # A single-required-file workstream binds the reported artifact unambiguously:
    # evidence.report_path must name that one required file, so the report the
    # participant points at IS the report the evaluator inspects (no two-file
    # ambiguity).
    report_path = evidence.get("report_path")
    if isinstance(report_path, str) and len(required_list) == 1:
        if report_path != required_list[0]:
            codes.append("report_path_not_required_file")
            details.append(
                f"evidence.report_path {report_path!r} must equal required_files[0] "
                f"{required_list[0]!r}"
            )
    unexpected = sorted(set(files) - allowed_files)
    missing = sorted(required_files - set(files))
    if unexpected:
        _append_failure(
            codes, details, "unexpected_files",
            "files outside the workstream contract: " + ", ".join(unexpected),
        )
    if missing:
        _append_failure(
            codes, details, "missing_required_files",
            "required files not reported: " + ", ".join(missing),
        )

    return codes, details


async def validate_completion_contract(
    workstream: dict[str, Any], event: dict[str, Any], workspace: WorkspaceRuntime,
) -> ResultContractValidation:
    """Validate payload claims and then run the private validator in the child workspace."""

    codes, details = validate_payload_contract(workstream, event)
    command = str(workstream.get("validator_command") or "").strip()
    exit_code: int | None = None
    output = ""
    # Fail fast at the declarative boundary. Running a filesystem validator
    # after the payload already violates its schema creates duplicate and often
    # misleading errors (for example a KeyError caused only by a missing field).
    # A replacement result should first repair the public/typed contract; only
    # then does the evaluator inspect the claimed child artifacts.
    if command and not codes:
        timeout = int(workstream.get("validator_timeout_sec") or 120)
        # Bind private validation to the exact hidden payload that reached the
        # gateway.  Base64 plus shell quoting keeps arbitrary model text out of
        # the command grammar while allowing case validators to compare dynamic
        # evidence (for example observed revisions) with the child artifacts.
        encoded_payload = base64.b64encode(
            json.dumps(
                event.get("payload"), ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).decode("ascii")
        bound_command = (
            f"export ASYNC_RBENCH_RESULT_PAYLOAD_B64={shlex.quote(encoded_payload)}\n"
            f"{command}"
        )
        result = await workspace.child_terminal(
            str(event.get("child_id", "")), bound_command, timeout,
        )
        exit_code = result.exit_code
        output = result.output[-4000:]
        if result.exit_code != 0:
            granular = classify_validator_output(output)
            if granular:
                for code, field in granular:
                    detail = f"report contract failed: {code}"
                    if field:
                        detail += f" (field {field})"
                    _append_failure(codes, details, code, detail)
            else:
                _append_failure(
                    codes, details, "reported_file_contract_failed",
                    f"evaluator-owned child validator exited with code {result.exit_code}",
                )

    return ResultContractValidation(
        valid=not codes,
        reason_codes=tuple(codes),
        details=tuple(details),
        validator_exit_code=exit_code,
        validator_output=output,
    )
