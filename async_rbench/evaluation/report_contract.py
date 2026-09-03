from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


# The accept/reject rule for a workstream that must write one report artifact is
# declared once, in the participant-visible ``public_result_contract``, and the
# evaluator-private ``validator_command`` is *rendered from it*.  This is what
# makes the contract transparent: there is no model-invisible structural
# constraint --- every assertion the validator makes is a pure function of the
# public rule.  A hand-typed validator_command that diverges from the public
# contract is a conformance violation and is rejected by the audit.
#
# Schema of ``public_result_contract`` (only for ``kind: report_file``):
# {
#   "kind": "report_file",
#   "report_file": {
#     "path": "<required_files[0]>",           # the single report artifact
#     "must_exist": true,
#     "must_be_valid_json": true,
#     "fields_equal_evidence": ["finding", "revision_sha256"],
#   }
# }
REPORT_FILE_KIND = "report_file"

CONTRACT_FAIL_TOKEN = "ASYNC_RBENCH_CONTRACT_FAIL"

# Granular, participant-safe codes for a report-file contract.  These are the
# actionable error codes the reject feedback carries so the model knows exactly
# what to repair.  They are distinct from the transport codes (payload/evidence
# shape) because they describe the *artifact* the model pointed at.
REPORT_CONTRACT_CODES = frozenset({
    "report_path_not_required_file",
    "report_file_missing",
    "report_json_invalid",
    "report_missing_required_field",
    "report_payload_field_mismatch",
})


def _report_contract(workstream: Mapping[str, Any]) -> Mapping[str, Any]:
    return dict(workstream.get("public_result_contract") or {})


def is_report_contract_workstream(workstream: Mapping[str, Any]) -> bool:
    return _report_contract(workstream).get("kind") == REPORT_FILE_KIND


def has_hidden_validator(workstream: Mapping[str, Any]) -> bool:
    """A private validator with no declared public accept rule (legacy gap)."""
    stage = str(workstream.get("validator_stage") or "")
    if stage == "semantic_evidence":
        return False
    return bool(str(workstream.get("validator_command") or "").strip()) and (
        stage != "submission_contract" or not is_report_contract_workstream(workstream)
    )


def report_file_config(workstream: Mapping[str, Any]) -> dict[str, Any]:
    """The validated ``report_file`` subtree, or ``{}`` when the workstream has
    no report contract (i.e. no declared report-file accept rule)."""
    contract = _report_contract(workstream)
    if contract.get("kind") != REPORT_FILE_KIND:
        return {}
    return dict(contract.get("report_file") or {})


def report_contract_errors(workstream: Mapping[str, Any]) -> list[str]:
    """Validate that a private validator is a faithful render of the public rule.

    A workstream with a ``validator_command`` but no public report contract (or
    a contract whose fields it does not enforce) hides an evaluator-only
    structurally constraint --- the exact defect this checklist removes.  The
    audit compares the authored command against ``render_validator_command`` so
    any drift surfaces as a contract violation rather than a silent private gate.
    """
    errors: list[str] = []
    command = str(workstream.get("validator_command") or "").strip()
    contract = _report_contract(workstream)
    required_files = [str(path) for path in workstream.get("required_files") or []]
    if not command:
        return errors
    stage = str(workstream.get("validator_stage") or "")
    if stage == "semantic_evidence":
        return errors
    if stage != "submission_contract":
        errors.append(f"unsupported validator_stage {stage!r}")
        return errors
    if contract.get("kind") != REPORT_FILE_KIND:
        errors.append("submission_contract requires public_result_contract.kind=report_file")
        return errors

    config = dict(contract.get("report_file") or {})
    path = str(config.get("path") or "")
    if not path:
        errors.append("report_file.path is empty")
    if required_files and path != required_files[0]:
        errors.append(
            f"report_file.path {path!r} != required_files[0] {required_files[0]!r}"
        )
    allowed = [str(item) for item in workstream.get("allowed_files") or []]
    if allowed and path not in allowed:
        errors.append(f"report_file.path {path!r} is not in allowed_files {allowed!r}")
    for name in config.get("fields_equal_evidence") or []:
        if str(name) not in (workstream.get("required_evidence_fields") or []):
            errors.append(
                f"report_file.fields_equal_evidence {name!r} is not a required evidence field"
            )
    if "'" in path:
        errors.append("report_file.path must not contain single quotes")
    command_render = render_validator_command(contract, required_files[0] if required_files else path)
    if command != command_render:
        errors.append(
            "validator_command is not the deterministic render of the public "
            "contract (contract drift -> hidden constraint). "
            f"got {len(command)} bytes, expected {len(command_render)} bytes"
        )
    return errors


def validator_code_lines(
    contract: Mapping[str, Any], required_file: str | None = None,
) -> list[str]:
    """The self-contained Python source of the report-file accept rule.

    It reads the submitted payload from ``ASYNC_RBENCH_RESULT_PAYLOAD_B64`` and
    reports the *first* violated rule via a ``ASYNC_RBENCH_CONTRACT_FAIL:<code>``
    line.  The report path is resolved under
    ``ASYNC_RBENCH_RESULT_WORKSPACE_ROOT`` (or ``/`` in a container) so the same
    program behaves identically on disk in Docker and on a host-side fixture.
    """
    config = dict(contract.get("report_file") or {})
    path = str(config.get("path") or required_file or "")
    fields = [str(field) for field in config.get("fields_equal_evidence") or []]
    must_exist = bool(config.get("must_exist", True))
    must_be_valid_json = bool(config.get("must_be_valid_json", True))

    lines: list[str] = [
        "import base64,json,os,pathlib,sys",
        "ev=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']",
        f"req={path!r}",
        f"fields={fields!r}",
        "if ev.get('report_path')!=req:",
        " print('ASYNC_RBENCH_CONTRACT_FAIL:report_path_not_required_file');sys.exit(1)",
        "root=pathlib.Path(os.environ.get('ASYNC_RBENCH_RESULT_WORKSPACE_ROOT') or '/')",
        "p=root.joinpath(*[part for part in req.split('/') if part])",
    ]
    if must_exist:
        lines += [
            "if not p.is_file():",
            " print('ASYNC_RBENCH_CONTRACT_FAIL:report_file_missing');sys.exit(1)",
        ]
    if must_be_valid_json:
        lines += [
            "if p.is_file():",
            " try:",
            "  r=json.load(open(p))",
            " except Exception:",
            "  print('ASYNC_RBENCH_CONTRACT_FAIL:report_json_invalid');sys.exit(1)",
            "else:",
            " r={}",
        ]
    else:
        lines.append("r={}")
    for field in fields:
        lines += [
            f"if {field!r} not in r:",
            f" print('ASYNC_RBENCH_CONTRACT_FAIL:report_missing_required_field:{field}');sys.exit(1)",
            f"if r[{field!r}]!=ev[{field!r}]:",
            f" print('ASYNC_RBENCH_CONTRACT_FAIL:report_payload_field_mismatch:{field}');sys.exit(1)",
        ]
    return lines


def render_validator_command(
    contract: Mapping[str, Any], required_file: str | None = None,
) -> str:
    """Render the evaluator-private ``validator_command`` from the public rule.

    The rendered command is a self-contained Python program (it must run in the
    child task container without importing the harness) wrapped as a
    ``python3 -c "..."`` invocation.  Because the public rule is the *only* thing
    it enforces, there is no model-invisible structural constraint.
    """
    code = "\n".join(validator_code_lines(contract, required_file))
    return f"python3 -c \"{code}\""


def run_report_validator(
    workstream: Mapping[str, Any],
    workspace_root: Path,
    payload: Mapping[str, Any],
    *,
    program: list[str] | None = None,
) -> tuple[int, list[tuple[str, str | None]]]:
    """Execute the rendered report-rule program against a host-side fixture root.

    This is the same code the Docker child runs, so a fixture that passes here
    is a genuine positive: it exercises the *private validator*, not just the
    transport payload check that ``audit_contract_fixtures`` used to run.
    """
    import base64
    import os
    import subprocess
    import sys

    lines = program if program is not None else validator_code_lines(
        _report_contract(workstream),
    )
    code = "\n".join(lines)
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    env = dict(os.environ)
    env["ASYNC_RBENCH_RESULT_PAYLOAD_B64"] = encoded
    env["ASYNC_RBENCH_RESULT_WORKSPACE_ROOT"] = str(workspace_root)
    process = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True,
    )
    return process.returncode, classify_validator_output(process.stdout + process.stderr)


def classify_validator_output(output: str) -> list[tuple[str, str | None]]:
    """Extract ``(code, field)`` pairs the rendered validator reports on failure."""
    found: list[tuple[str, str | None]] = []
    prefix = f"{CONTRACT_FAIL_TOKEN}:"
    for line in output.splitlines():
        for part in line.split():
            if not part.startswith(prefix):
                continue
            token = part[len(prefix):]
            code, separator, field = token.partition(":")
            found.append((code, field if separator else None))
    return found


def fixture_value(
    field_name: str, field_schema: Mapping[str, Any], report_path: str,
) -> Any:
    """Return one deterministic value satisfying the supported evidence schema."""
    schema = dict(field_schema or {})
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return list(schema["enum"])[0]
    if field_name == "report_path":
        return report_path
    if schema.get("pattern") == "^[0-9a-f]{64}$":
        return "0" * 64
    expected_type = str(schema.get("type") or "")
    if expected_type == "string":
        return "fixture-value"
    if expected_type == "integer":
        return 1
    if expected_type == "number":
        return 1.0
    if expected_type == "boolean":
        return True
    if expected_type == "array":
        return ["fixture-value"] * int(schema.get("min_items") or 0)
    if expected_type == "object":
        return {}
    raise ValueError(
        f"cannot build fixture for evidence field {field_name!r} with schema {schema!r}"
    )


def build_report_fixture(
    workstream: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a positive + negative fixture payload set for a report workstream.

    Every negative is a copy of the positive payload with exactly one rule
    violated, keyed by the granular code it must trigger.  Returns ``{}`` for
    workstreams without a report contract or without a single required file.
    """
    config = report_file_config(workstream)
    if not config:
        return {}
    required_files = [str(path) for path in workstream.get("required_files") or []]
    if len(required_files) != 1:
        return {}
    report_path = str(config.get("path") or required_files[0])
    fields = [str(field) for field in config.get("fields_equal_evidence") or []]
    schema = dict(workstream.get("evidence_schema") or {})
    try:
        evidence = {
            str(field_name): fixture_value(
                str(field_name), dict(schema.get(str(field_name)) or {}), report_path,
            )
            for field_name in workstream.get("required_evidence_fields") or []
        }
    except ValueError:
        return {}
    positive = {
        "type": "child_completed",
        "payload": {
            "summary": "report fixture positive",
            "evidence": evidence,
            "files": [report_path],
        },
    }
    negatives: dict[str, dict[str, Any]] = {}
    missing_field_negatives: dict[str, dict[str, Any]] = {}
    mismatch_negatives: dict[str, dict[str, Any]] = {}

    def clone() -> dict[str, Any]:
        return json.loads(json.dumps(positive))

    # Workspace-state negatives: the payload is identical to the positive, but the
    # on-disk artifact is missing / malformed / incomplete.  The fixture staging
    # mutates the file system for these; the payload alone cannot express them.
    if bool(config.get("must_exist", True)):
        negatives["report_file_missing"] = clone()
    if bool(config.get("must_be_valid_json", True)):
        negatives["report_json_invalid"] = clone()
    for field in fields:
        missing_field_negatives[field] = clone()
        mismatch = clone()
        original = mismatch["payload"]["evidence"][field]
        mismatch["payload"]["evidence"][field] = (
            not original if isinstance(original, bool)
            else original + 1 if isinstance(original, (int, float))
            else [*original, "different"] if isinstance(original, list)
            else {"different": True} if isinstance(original, dict)
            else f"{original}-different"
        )
        mismatch_negatives[field] = mismatch
    if fields:
        negatives["report_missing_required_field"] = missing_field_negatives[fields[0]]
        negatives["report_payload_field_mismatch"] = mismatch_negatives[fields[0]]

    wrong_path = clone()
    wrong_path["payload"]["evidence"]["report_path"] = "/app/output_data/workstreams/other.json"
    negatives["report_path_not_required_file"] = wrong_path

    return {
        "report_path": report_path,
        "fields_equal_evidence": fields,
        "positive": positive,
        "negatives": negatives,
        "missing_field_negatives": missing_field_negatives,
        "mismatch_negatives": mismatch_negatives,
    }


def prepare_report_fixture_workspace(
    workstream: Mapping[str, Any], workspace_root: Path,
) -> dict[str, Path]:
    """Materialise the report file for a positive fixture under ``workspace_root``.

    Returns the on-disk paths keyed by a case label so the fixture harness can
    stage the exact positive file, and (for negative cases) remove it or swap
    its contents before invoking the validator command.
    """
    fixture = build_report_fixture(workstream)
    if not fixture:
        return {}
    report_path = str(fixture["report_path"])
    target = workspace_root.joinpath(*[part for part in report_path.split("/") if part])
    target.parent.mkdir(parents=True, exist_ok=True)
    evidence = fixture["positive"]["payload"]["evidence"]
    fields = list(fixture["fields_equal_evidence"])
    target.write_text(
        json.dumps({field: evidence[field] for field in fields}, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"positive": target}


def locate_fixture_report_file(fixture: dict[str, Any], workspace_root: Path) -> Path:
    return workspace_root.joinpath(
        *[part for part in str(fixture["report_path"]).split("/") if part]
    )
