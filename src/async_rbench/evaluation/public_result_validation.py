from __future__ import annotations

import base64
import json
import shlex
from pathlib import PurePosixPath
from typing import Any, Mapping

from .report_contract import classify_validator_output, render_validator_command
from .result_contract import ResultContractValidation, validate_payload_contract
from .workspace_runtime import WorkspaceRuntime


PUBLIC_CONTRACT_KINDS = frozenset({"payload_only", "report_file"})


def validate_public_contract_definition(
    workstream: Mapping[str, Any],
) -> tuple[str, ...]:
    errors: list[str] = []
    contract = workstream.get("public_result_contract")
    if not isinstance(contract, Mapping):
        return ("public_result_contract must be an object",)
    kind = contract.get("kind")
    if not kind:
        return ("public_result_contract.kind is required",)
    if kind not in PUBLIC_CONTRACT_KINDS:
        return (f"unsupported public_result_contract.kind {kind!r}",)
    if kind == "payload_only":
        return ()

    config = contract.get("report_file")
    if not isinstance(config, Mapping):
        return ("public_result_contract.report_file must be an object",)
    path = str(config.get("path") or "")
    if not path:
        errors.append("report_file.path is required")
    else:
        parsed = PurePosixPath(path)
        if not path.startswith("/app/") or ".." in parsed.parts:
            errors.append("report_file.path must be an absolute /app path without '..'")
    required_files = [str(item) for item in workstream.get("required_files") or []]
    if len(required_files) != 1:
        errors.append("report_file requires exactly one required_files entry")
    elif path and path != required_files[0]:
        errors.append("report_file.path must equal the single required_files entry")
    allowed_files = [str(item) for item in workstream.get("allowed_files") or []]
    if path and path not in allowed_files:
        errors.append("report_file.path must be present in allowed_files")
    fields = list(config.get("fields_equal_evidence") or [])
    if any(not isinstance(item, str) or not item for item in fields):
        errors.append("report_file.fields_equal_evidence must contain non-empty strings")
    if len(fields) != len(set(fields)):
        errors.append("report_file.fields_equal_evidence must be unique")
    required_evidence = set(
        str(item) for item in workstream.get("required_evidence_fields") or []
    )
    if "report_path" not in required_evidence:
        errors.append("report_file requires report_path in required_evidence_fields")
    unknown = sorted(set(fields) - required_evidence)
    if unknown:
        errors.append(
            "report_file.fields_equal_evidence must be a subset of "
            f"required_evidence_fields: {unknown!r}"
        )
    if fields and not bool(config.get("must_be_valid_json", True)):
        errors.append(
            "report_file.must_be_valid_json must be true when fields_equal_evidence is non-empty"
        )
    if fields and not bool(config.get("must_exist", True)):
        errors.append(
            "report_file.must_exist must be true when fields_equal_evidence is non-empty"
        )
    return tuple(errors)


async def validate_public_submission(
    workstream: Mapping[str, Any],
    event: Mapping[str, Any],
    workspace: WorkspaceRuntime,
) -> ResultContractValidation:
    definition_errors = validate_public_contract_definition(workstream)
    if definition_errors:
        return ResultContractValidation(
            valid=False,
            reason_codes=("invalid_public_result_contract",),
            details=definition_errors,
        )

    public_workstream = dict(workstream)
    if isinstance(workstream.get("public_evidence_schema"), Mapping):
        public_workstream["evidence_schema"] = dict(
            workstream.get("public_evidence_schema") or {}
        )
    codes, details = validate_payload_contract(public_workstream, dict(event))
    if codes:
        return ResultContractValidation(False, tuple(codes), tuple(details))

    contract = dict(workstream.get("public_result_contract") or {})
    if contract.get("kind") == "payload_only":
        return ResultContractValidation(True, (), ())

    config = dict(contract.get("report_file") or {})
    payload = dict(event.get("payload") or {})
    evidence = dict(payload.get("evidence") or {})
    report_path = str(config["path"])
    if evidence.get("report_path") != report_path:
        return ResultContractValidation(
            False,
            ("report_path_not_required_file",),
            (f"evidence.report_path must equal {report_path!r}",),
        )

    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).decode("ascii")
    command = render_validator_command(contract, report_path)
    bound = (
        f"export ASYNC_RBENCH_RESULT_PAYLOAD_B64={shlex.quote(encoded)}\n{command}"
    )
    result = await workspace.child_terminal(
        str(event.get("child_id") or ""),
        bound,
        int(workstream.get("validator_timeout_sec") or 120),
    )
    output = result.output[-4000:]
    failure_codes: list[str] = []
    failure_details: list[str] = []
    if result.exit_code != 0:
        granular = classify_validator_output(output)
        if granular:
            for code, field in granular:
                if code not in failure_codes:
                    failure_codes.append(code)
                failure_details.append(
                    f"report contract failed: {code}"
                    + (f" (field {field})" if field else "")
                )
        else:
            failure_codes.append("reported_file_contract_failed")
            failure_details.append(
                f"public report validator exited with code {result.exit_code}"
            )
    return ResultContractValidation(
        not failure_codes,
        tuple(failure_codes),
        tuple(failure_details),
        validator_exit_code=result.exit_code,
        validator_output=output,
    )
