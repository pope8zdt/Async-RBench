from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

from .case_contract import PUBLIC_RESULT_REJECTION_CODES
from .protocol import load_trace
from .report_contract import (
    REPORT_CONTRACT_CODES,
    has_hidden_validator,
    report_contract_errors,
)
from .result_contract import validate_payload_contract
from .termination import classify_child_terminals
from ..spec import case_instance_key, discover_case_instances


#: Every hard-fail reason an ``audit_run`` report can carry.  ``audit-run`` maps
#: each to a pass-gate (Task 10) so a certification cannot silently proceed when
#: the benchmark fixtures fail, a submission-stage validator hides a constraint,
#: a private-only rejection reached the scorer, a spawned child was still in
#: flight when its episode closed, or an official Linear run recorded no main
#: measurement.
AUDIT_HARD_FAIL_REASONS = (
    "contract_fixture_failure",
    "hidden_submission_constraint",
    "private_submission_rejection",
    "unknown_child_terminal",
    "official_linear_zero_main_tokens",
)


def child_terminal_integrity_violations(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split per-attempt classification rows into mechanism defects.

    Returns ``(private_only_rejections, unknown_terminals)``:

    * a *private-only rejection* is a ``case_contract_failure`` row carrying
      rejection reason codes but no actionable public code — a private check
      leaked into the gateway verdict (Task 4);
    * an *unknown terminal* is a row still classified ``in_flight`` after its
      episode closed — the spawned child never reached a concrete runtime
      terminal (Task 1/8).

    Neither is ever a model submission verdict; both block a certification.
    """
    private_only: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for row in rows:
        terminal_class = str(row.get("terminal_class") or "")
        if terminal_class == "case_contract_failure" and (
            row.get("reason_codes")
        ) and not (row.get("public_codes")):
            private_only.append(row)
        elif terminal_class == "in_flight":
            unknown.append(row)
    return private_only, unknown


def _pattern_value(pattern: str) -> str:
    """Create a deterministic value for the small regex subset used by cases."""
    unanchored = pattern.removeprefix("^").removesuffix("$")
    match = re.fullmatch(r"(.*)\[0-9a-f\]\{(\d+)\}", unanchored)
    if match:
        return match.group(1) + ("0" * int(match.group(2)))
    if pattern == r"^/app/output_data/workstreams/.+\.json$":
        return "/app/output_data/workstreams/fixture.json"
    raise ValueError(f"contract fixture cannot synthesize pattern {pattern!r}")


def synthesize_evidence_value(field_spec: dict[str, Any]) -> Any:
    if "const" in field_spec:
        return field_spec["const"]
    if field_spec.get("enum"):
        return list(field_spec["enum"])[0]
    if "pattern" in field_spec:
        return _pattern_value(str(field_spec["pattern"]))
    expected_type = str(field_spec.get("type"))
    minimum = int(field_spec.get("min_items") or 0)
    if expected_type == "string":
        return "x" * max(1, minimum)
    if expected_type == "integer":
        return 1
    if expected_type == "number":
        return 1.0
    if expected_type == "boolean":
        return True
    if expected_type == "array":
        return ["fixture"] * minimum
    if expected_type == "object":
        return {f"fixture_{index}": True for index in range(minimum)}
    raise ValueError(f"unsupported evidence type {expected_type!r}")


def structural_fixture_result(workstream: dict[str, Any]) -> dict[str, Any]:
    schema = dict(workstream.get("evidence_schema") or {})
    evidence = {
        field_name: synthesize_evidence_value(dict(schema[field_name]))
        for field_name in workstream.get("required_evidence_fields") or []
    }
    required_files = [str(path) for path in workstream.get("required_files") or []]
    # report_path names the artifact the evaluator inspects; when the contract
    # pins it to exactly one required file, the fixture must point there (P0-3)
    # rather than at the schema-pattern placeholder, or the positive fixture would
    # fail the report-path alignment check for a reason unrelated to the rule.
    if "report_path" in evidence and len(required_files) == 1:
        evidence["report_path"] = required_files[0]
    return {
        "type": "child_completed",
        "payload": {
            "summary": "contract audit fixture",
            "evidence": evidence,
            "files": list(workstream.get("required_files") or []),
        },
    }


def _private_fixture_result(
    workstream: dict[str, Any],
    *,
    validator_timeout: float | None = None,
) -> dict[str, Any]:
    """Execute the actual private validator on a positive + negative fixture.

    Unlike the transport-level fixture check (which only runs
    ``validate_payload_contract``), this stages a real report artifact on a local
    workspace root and runs the same rendered validator program the Docker child
    would run.  A workstream passes only when its positive fixture is accepted
    and every negative fixture trips exactly the intended granular code.
    """
    import tempfile

    from .report_contract import build_report_fixture, locate_fixture_report_file, run_report_validator

    fixture = build_report_fixture(workstream)
    if not fixture:
        return {"supported": False, "reason": "no single-report-file contract"}
    positive = fixture["positive"]
    evidence = positive["payload"]["evidence"]
    negative_payloads = fixture["negatives"]
    fields = list(fixture["fields_equal_evidence"])

    with tempfile.TemporaryDirectory(prefix="async_rbench-fixture-") as td:
        workspace_root = Path(td)
        report_file = locate_fixture_report_file(fixture, workspace_root)
        report_file.parent.mkdir(parents=True, exist_ok=True)

        def stage_valid() -> None:
            report_file.write_text(
                json.dumps({field: evidence[field] for field in fields}, ensure_ascii=False),
                encoding="utf-8",
            )

        stage_valid()
        positive_code, positive_marks = run_report_validator(
            workstream, workspace_root, positive["payload"],
            timeout=validator_timeout,
        )
        positive_passed = positive_code == 0 and not positive_marks

        negatives: dict[str, dict[str, Any]] = {}
        for code, negative_payload in negative_payloads.items():
            stage_valid()
            if code == "report_file_missing":
                report_file.unlink(missing_ok=True)
            elif code == "report_json_invalid":
                report_file.write_text("{not valid json", encoding="utf-8")
            elif code == "report_missing_required_field":
                missing_field = fields[0]
                report_file.write_text(
                    json.dumps({
                        field: evidence[field] for field in fields if field != missing_field
                    }, ensure_ascii=False),
                    encoding="utf-8",
                )
            elif code == "report_payload_field_mismatch":
                stage_valid()
            elif code == "report_path_not_required_file":
                # The payload tells the validator to look somewhere else; the file
                # content is irrelevant because the alignment check fires first.
                pass
            run_code, run_marks = run_report_validator(
                workstream, workspace_root, negative_payload["payload"],
                timeout=validator_timeout,
            )
            triggered = [mark[0] for mark in run_marks]
            negatives[code] = {
                "triggered_codes": triggered,
                "expected_code": code,
                "passed": bool(run_code != 0 and code in triggered),
            }
        for field, negative_payload in fixture["missing_field_negatives"].items():
            stage_valid()
            report_file.write_text(
                json.dumps({
                    name: evidence[name] for name in fields if name != field
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            run_code, run_marks = run_report_validator(
                workstream, workspace_root, negative_payload["payload"],
                timeout=validator_timeout,
            )
            triggered = [mark[0] for mark in run_marks]
            negatives[f"report_missing_required_field:{field}"] = {
                "triggered_codes": triggered,
                "expected_code": "report_missing_required_field",
                "passed": bool(
                    run_code != 0 and "report_missing_required_field" in triggered
                ),
            }
        for field, negative_payload in fixture["mismatch_negatives"].items():
            stage_valid()
            run_code, run_marks = run_report_validator(
                workstream, workspace_root, negative_payload["payload"],
                timeout=validator_timeout,
            )
            triggered = [mark[0] for mark in run_marks]
            negatives[f"report_payload_field_mismatch:{field}"] = {
                "triggered_codes": triggered,
                "expected_code": "report_payload_field_mismatch",
                "passed": bool(
                    run_code != 0 and "report_payload_field_mismatch" in triggered
                ),
            }

    return {
        "supported": True,
        "report_path": fixture["report_path"],
        "positive_passed": positive_passed,
        "negatives": negatives,
    }


def _audit_workstream(
    case: Any,
    instance: Any,
    workstream: dict[str, Any],
    sufficiency: dict[str, Any],
    *,
    validator_timeout: float | None = None,
) -> tuple[dict[str, Any], bool, str, bool]:
    """Evaluate one workstream's public/private contract fixtures + P0-4 drift.

    Runs independently (its only side effects are its return values), so
    ``audit_contract_fixtures`` can fan the subprocess-heavy private-validator
    checks across threads.  Returns ``(row, passed, failure, hidden_submission
    constraint)``.
    """
    stream_id = str(workstream.get("id"))
    event = structural_fixture_result(workstream)
    positive_codes, _ = validate_payload_contract(workstream, event)
    required = list(workstream.get("required_evidence_fields") or [])
    negative_event = json.loads(json.dumps(event))
    expected_negative_code = "missing_required_evidence"
    if required:
        negative_event["payload"]["evidence"].pop(required[0])
    else:
        negative_event["payload"]["files"] = ["/not/allowed"]
        expected_negative_code = "unexpected_files"
    negative_codes, _ = validate_payload_contract(workstream, negative_event)
    public_schema = dict(workstream.get("public_evidence_schema") or {})
    private_schema = dict(workstream.get("evidence_schema") or {})
    schema_names_match = set(public_schema) == set(private_schema) == set(required)
    public_types_match = all(
        public_schema.get(name, {}).get("type") == private_schema.get(name, {}).get("type")
        for name in required
    )
    sufficiency_fields = set(
        (sufficiency.get(stream_id) or {}).get("required_output_fields") or []
    )
    sufficiency_matches = sufficiency_fields == set(required)
    # P0-4: the evaluator-private validator must be a faithful render of
    # the participant-visible public contract — no hidden constraint.
    contract_drift = report_contract_errors(workstream)
    stage = str(workstream.get("validator_stage") or "")
    public_kind = str(
        (workstream.get("public_result_contract") or {}).get("kind") or ""
    )
    public_contract_declared = public_kind in {"payload_only", "report_file"}
    validator_stage_valid = bool(
        (stage == "semantic_evidence" and public_kind == "payload_only")
        or (
            stage == "submission_contract"
            and public_kind == "report_file"
            and not contract_drift
        )
    )
    hidden_submission_constraint = bool(
        has_hidden_validator(workstream)
        or (stage == "submission_contract" and not validator_stage_valid)
    )
    # P0-5: actually execute the private validator on a positive + negative
    # fixture (the audit previously ran only validate_payload_contract).
    private_fixture = (
        _private_fixture_result(workstream, validator_timeout=validator_timeout)
        if stage == "submission_contract"
        else {"supported": False, "reason": "semantic validator is diagnostic"}
    )
    private_fixture_passed = bool(
        stage == "semantic_evidence"
        or (
            private_fixture["supported"]
            and private_fixture["positive_passed"]
            and all(item["passed"] for item in private_fixture["negatives"].values())
        )
    )
    passed = bool(
        not positive_codes
        and expected_negative_code in negative_codes
        and schema_names_match
        and public_types_match
        and sufficiency_matches
        and public_contract_declared
        and validator_stage_valid
        and not hidden_submission_constraint
        and not contract_drift
        and private_fixture_passed
    )
    row = {
        "case_id": case.case_id,
        "instance_id": instance.instance_id,
        "workstream_id": stream_id,
        "positive_fixture_passed": not positive_codes,
        "positive_reason_codes": positive_codes,
        "negative_fixture_passed": expected_negative_code in negative_codes,
        "negative_reason_codes": negative_codes,
        "public_private_schema_names_match": schema_names_match,
        "public_private_types_match": public_types_match,
        "information_sufficiency_fields_match": sufficiency_matches,
        "validator_stage_valid": validator_stage_valid,
        "public_contract_declared": public_contract_declared,
        "private_fixture_supported": bool(private_fixture["supported"]),
        "hidden_submission_constraint": hidden_submission_constraint,
        "private_validator_executed": bool(private_fixture["supported"]),
        "private_positive_passed": private_fixture.get("positive_passed"),
        "private_negatives": private_fixture.get("negatives", {}),
        "contract_drift_errors": contract_drift,
        "private_fixture_passed": private_fixture_passed,
        "passed": passed,
    }
    failure = f"{case.case_id}/{instance.instance_id}/{stream_id}" if not passed else ""
    return row, passed, failure, hidden_submission_constraint


def audit_contract_fixtures(
    root: Path,
    *,
    validator_timeout: float | None = 30.0,
    progress: bool = False,
) -> dict[str, Any]:
    """Audit every case's workstream contract fixtures (public + private).

    The submission-stage private-validator check shells out to the rendered
    validator program, which is the dominant cost (hundreds of subprocess
    launches).  Cases are loaded once, then the per-workstream evaluation is
    fanned across a thread pool so the audit scales with available cores instead
    of summing those launches serially.  ``validator_timeout`` bounds each
    subprocess so a hung validator cannot stall the audit, and ``progress``
    emits a running counter to stderr for long CLI runs.
    """
    jobs: list[tuple[Any, Any, dict[str, Any], dict[str, Any]]] = []
    for instance in discover_case_instances(root):
        case = instance.load()
        sufficiency = {
            str(item.get("workstream_id")): item
            for item in case.raw.get("information_sufficiency") or []
        }
        for workstream in case.raw.get("delegation_workstreams") or []:
            jobs.append((case, instance, workstream, sufficiency))

    total = len(jobs)
    workers = min(32, (os.cpu_count() or 1) * 4)
    results: list[tuple[dict[str, Any], bool, str, bool]] = []
    if total == 0:
        results = []
    elif workers <= 1 or total == 1:
        results = [
            _audit_workstream(case, instance, workstream, sufficiency, validator_timeout=validator_timeout)
            for case, instance, workstream, sufficiency in jobs
        ]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _audit_workstream, case, instance, workstream, sufficiency,
                    validator_timeout=validator_timeout,
                )
                for case, instance, workstream, sufficiency in jobs
            ]
            for index, future in enumerate(futures):
                results.append(future.result())
                if progress and (index + 1) % 25 == 0:
                    sys.stderr.write(f"\raudit fixtures {index + 1}/{total}")
                    sys.stderr.flush()
    if progress and total:
        sys.stderr.write(f"\raudit fixtures {total}/{total}\n")
        sys.stderr.flush()

    rows = [item[0] for item in results]
    failures = [item[2] for item in results if item[2]]
    return {
        "workstream_count": len(rows),
        "passed_count": sum(bool(row["passed"]) for row in rows),
        "failed_workstreams": failures,
        "passed": not failures,
        "hidden_validator_workstream_count": sum(1 for item in results if item[3]),
        "note": "hidden submission constraints fail the contract audit closed",
        "workstreams": rows,
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _episode_audit(score_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    score = json.loads(score_path.read_text(encoding="utf-8"))
    trace_path = score_path.with_name("event_source.jsonl")
    events = load_trace(trace_path)
    child_workstreams = {
        str(event.get("child_id")): str((event.get("work_units") or [""])[0])
        for event in events if event.get("type") == "child_spawned"
    }
    private_rejections = {
        str(event.get("completion_id")): event
        for event in events if event.get("type") == "result_rejection_evaluator_fact"
    }
    validations = {
        str(event.get("completion_id")): event
        for event in events if event.get("type") == "result_contract_validated"
    }
    completions = {
        str(event.get("completion_id")): event
        for event in events if event.get("type") == "child_completed"
    }
    outcomes: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") not in {"result_delivered", "result_rejected"}:
            continue
        completion_id = str(event.get("completion_id"))
        private = private_rejections.get(completion_id, {})
        validation = validations.get(completion_id, {})
        completion = completions.get(completion_id, {})
        payload = completion.get("payload")
        evidence = payload.get("evidence") if isinstance(payload, dict) else None
        private_codes = [str(code) for code in private.get("reason_codes") or []]
        child_budget_exhausted = bool(
            isinstance(evidence, dict) and evidence.get("turn_budget_exhausted") is True
        )
        if event.get("type") == "result_delivered":
            root_cause = "accepted"
        elif child_budget_exhausted:
            root_cause = "child_budget_exhausted"
        elif "report_path_not_required_file" in private_codes:
            root_cause = "participant_structural_contract_violation"
        elif any(code in REPORT_CONTRACT_CODES for code in private_codes):
            root_cause = "participant_report_artifact_failed"
        elif any(code in PUBLIC_RESULT_REJECTION_CODES for code in private_codes):
            root_cause = "participant_structural_contract_violation"
        elif "evidence_constraint_failed" in private_codes:
            root_cause = "participant_evidence_claim_mismatch"
        elif "validator_command_failed" in private_codes:
            root_cause = "participant_artifact_validation_failed"
        else:
            root_cause = "unclassified_rejection"
        validator_output = str(validation.get("validator_output") or "")
        validator_signal = None
        if "KeyError:" in validator_output:
            validator_signal = "artifact_json_missing_field"
        elif "JSONDecodeError" in validator_output:
            validator_signal = "artifact_json_invalid"
        elif "SyntaxError" in validator_output:
            validator_signal = "artifact_source_invalid"
        elif "AssertionError" in validator_output:
            validator_signal = "validator_assertion_failed"
        elif validation.get("validator_exit_code") not in {None, 0}:
            validator_signal = "validator_command_nonzero"
        outcomes.append({
            "case_id": score.get("case_id"),
            "instance_id": score.get("instance_id", "seed-1"),
            "execution_mode": score.get("execution_mode"),
            "episode_id": score.get("episode_id"),
            "workstream_id": event.get("workstream_id") or child_workstreams.get(str(event.get("child_id"))),
            "completion_id": completion_id,
            "outcome": "accepted" if event.get("type") == "result_delivered" else "rejected",
            "root_cause": root_cause,
            "child_budget_exhausted": child_budget_exhausted,
            "public_reason_codes": list(event.get("reason_codes") or []),
            "private_reason_codes": private_codes,
            "has_public_structural_reason": any(
                code in PUBLIC_RESULT_REJECTION_CODES for code in private_codes
            ),
            "publicly_actionable": bool(private_codes) and all(
                code in PUBLIC_RESULT_REJECTION_CODES for code in private_codes
            ),
            "requires_private_validator_review": any(
                code not in PUBLIC_RESULT_REJECTION_CODES for code in private_codes
            ),
            "validator_exit_code": validation.get("validator_exit_code"),
            "validator_signal": validator_signal,
            "validation_details": list(validation.get("details") or []),
            "validator_output_tail": validator_output[-1000:],
        })

    finished = [
        event for event in events
        if event.get("type") == "agent_progress"
        and event.get("phase") == "model_call_finished"
    ]
    metadata = score.get("participant_metadata") or {}
    ends = [event for event in events if event.get("type") == "episode_ended"]
    local_status = ends[-1].get("local_status") if ends else None
    terminal_rows = classify_child_terminals(events)
    episode_closed = bool(ends)
    main_turns = max(
        (int(event.get("turn", 0)) for event in finished if event.get("role") == "main"),
        default=0,
    )
    child_turns: dict[str, int] = defaultdict(int)
    for event in finished:
        role = str(event.get("role", ""))
        if role.startswith("child:"):
            child_turns[role.removeprefix("child:")] = max(
                child_turns[role.removeprefix("child:")], int(event.get("turn", 0)),
            )
    main_limit = int(metadata.get("max_main_turns") or 0)
    child_limit = int(metadata.get("max_child_turns") or 0)
    child_limit_hits = sorted(
        child_id for child_id, turns in child_turns.items()
        if child_limit and turns >= child_limit
    )
    child_budget_exhausted_ids = sorted({
        str(event.get("child_id"))
        for event in events
        if event.get("type") == "child_completed"
        and isinstance(event.get("payload"), dict)
        and isinstance(event["payload"].get("evidence"), dict)
        and event["payload"]["evidence"].get("turn_budget_exhausted") is True
    })
    episode = {
        "case_id": score.get("case_id"),
        "instance_id": score.get("instance_id", "seed-1"),
        "execution_mode": score.get("execution_mode"),
        "episode_id": score.get("episode_id"),
        "score_status": score.get("score_status"),
        "local_status": local_status,
        "episode_closed": episode_closed,
        "leaderboard_eligible": bool(score.get("leaderboard_eligible")),
        "child_terminal_classifications": terminal_rows,
        "budget_exhausted": local_status == "budget_exhausted",
        "main_model_calls": sum(event.get("role") == "main" for event in finished),
        "child_model_calls": sum(str(event.get("role", "")).startswith("child:") for event in finished),
        "main_turn_limit": main_limit or None,
        "max_observed_main_turn": main_turns,
        "main_turn_limit_reached": bool(main_limit and main_turns >= main_limit),
        "child_turn_limit": child_limit or None,
        "child_turn_limit_hit_ids": child_limit_hits,
        "child_budget_exhausted_ids": child_budget_exhausted_ids,
        "result_contract_rejected_count": score.get("result_contract_rejected_count", 0),
        "main_tokens": score.get("main_tokens", 0),
        "child_tokens": score.get("child_tokens", 0),
        "total_tokens": score.get("total_tokens", 0),
        "episode_duration_ms": score.get("episode_duration_ms", 0.0),
        "recorded_case_sha256": score.get("case_sha256"),
        "recorded_scaffold_and_protocol_sha256": score.get("scaffold_and_protocol_sha256"),
        "recorded_evaluation_contract_sha256": score.get("evaluation_contract_sha256"),
    }
    return episode, outcomes


def audit_run(
    root: Path, benchmark_root: Path, *, contract_fixtures: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Imported lazily to keep the audit helpers usable without initializing the
    # episode runner during module import.
    from .runner import _case_digest, _source_digest

    score_paths = sorted(
        path for path in root.rglob("score.json")
        if not any(part.startswith(".") for part in path.relative_to(root).parts)
    )
    episodes: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for score_path in score_paths:
        event_source = score_path.with_name("event_source.jsonl")
        if not event_source.is_file():
            continue
        episode, episode_outcomes = _episode_audit(score_path)
        episodes.append(episode)
        outcomes.extend(episode_outcomes)

    private_reason_counts = Counter(
        code for outcome in outcomes for code in outcome["private_reason_codes"]
    )
    public_reason_counts = Counter(
        code for outcome in outcomes for code in outcome["public_reason_codes"]
    )
    root_cause_counts = Counter(
        str(outcome["root_cause"]) for outcome in outcomes
        if outcome["outcome"] == "rejected"
    )
    workstream_rows: dict[tuple[str, str, str, str], Counter[str]] = defaultdict(Counter)
    for outcome in outcomes:
        key = (
            str(outcome["case_id"]), str(outcome.get("instance_id") or "seed-1"),
            str(outcome["execution_mode"]),
            str(outcome["workstream_id"]),
        )
        workstream_rows[key][str(outcome["outcome"])] += 1
        workstream_rows[key]["publicly_actionable"] += int(outcome["publicly_actionable"])
        workstream_rows[key]["has_public_structural_reason"] += int(
            outcome["has_public_structural_reason"]
        )
        workstream_rows[key]["private_validator_review"] += int(outcome["requires_private_validator_review"])
    per_workstream = [
        {
            "case_id": key[0], "instance_id": key[1],
            "execution_mode": key[2], "workstream_id": key[3],
            "accepted": counts["accepted"], "rejected": counts["rejected"],
            "publicly_actionable_rejections": counts["publicly_actionable"],
            "rejections_with_public_structural_reason": counts["has_public_structural_reason"],
            "private_validator_review_rejections": counts["private_validator_review"],
        }
        for key, counts in sorted(workstream_rows.items())
    ]
    tokens = [float(item.get("total_tokens") or 0) for item in episodes]
    durations = [float(item.get("episode_duration_ms") or 0) for item in episodes]
    # A caller (e.g. a session-scoped test fixture) may hand over a pre-computed
    # full-corpus audit rather than pay the subprocess-heavy scan again.
    fixtures = (
        audit_contract_fixtures(benchmark_root)
        if contract_fixtures is None else contract_fixtures
    )
    current_source_digest = _source_digest(benchmark_root)
    current_contract_digest = hashlib.sha256(
        (benchmark_root / "evaluation_contract.json").read_bytes()
    ).hexdigest()
    current_case_digests = {
        case_instance_key(instance.case_id, instance.instance_id):
            _case_digest(instance.case_dir)
        for instance in discover_case_instances(benchmark_root)
    }
    for episode in episodes:
        case_id = str(episode.get("case_id"))
        instance_id = str(episode.get("instance_id") or "seed-1")
        digest_key = case_instance_key(case_id, instance_id)
        episode["current_case_sha256"] = current_case_digests.get(digest_key)
        episode["case_contract_matches_current"] = (
            episode.get("recorded_case_sha256") == current_case_digests.get(digest_key)
        )
        episode["scaffold_matches_current"] = (
            episode.get("recorded_scaffold_and_protocol_sha256") == current_source_digest
        )
        episode["evaluation_contract_matches_current"] = (
            episode.get("recorded_evaluation_contract_sha256") == current_contract_digest
        )
    # Task 10: audit-run hard gates.  A delivered run root must not certify when
    # the benchmark fixtures fail, a submission-stage validator hides a private
    # constraint, a private-only rejection reached the scorer, a spawned child
    # was still in flight once its episode closed, or an official Linear run
    # recorded zero main-side measurement.
    private_only_episode_ids = sorted({
        str(episode.get("episode_id"))
        for episode in episodes
        if child_terminal_integrity_violations(
            episode.get("child_terminal_classifications") or [],
        )[0]
    })
    unknown_terminal_episode_ids = sorted({
        str(episode.get("episode_id"))
        for episode in episodes
        if episode.get("episode_closed") is True
        and child_terminal_integrity_violations(
            episode.get("child_terminal_classifications") or [],
        )[1]
    })
    official_linear_zero_main_episode_ids = sorted({
        str(episode.get("episode_id"))
        for episode in episodes
        if str(episode.get("execution_mode")) == "linear"
        and episode.get("leaderboard_eligible") is True
        and int(episode.get("main_tokens") or 0) == 0
    })
    hard_fail_reasons: list[str] = []
    if fixtures["passed"] is not True:
        hard_fail_reasons.append("contract_fixture_failure")
    if int(fixtures.get("hidden_validator_workstream_count") or 0) > 0:
        hard_fail_reasons.append("hidden_submission_constraint")
    if private_only_episode_ids:
        hard_fail_reasons.append("private_submission_rejection")
    if unknown_terminal_episode_ids:
        hard_fail_reasons.append("unknown_child_terminal")
    if official_linear_zero_main_episode_ids:
        hard_fail_reasons.append("official_linear_zero_main_tokens")

    all_workstream_keys = {
        (
            str(row["case_id"]), str(row.get("instance_id") or "seed-1"),
            str(row["workstream_id"]),
        )
        for row in fixtures["workstreams"]
    }
    accepted_workstream_keys = {
        (
            str(outcome["case_id"]), str(outcome.get("instance_id") or "seed-1"),
            str(outcome["workstream_id"]),
        )
        for outcome in outcomes if outcome["outcome"] == "accepted"
    }
    missing_positive_observation = [
        {
            "case_id": case_id, "instance_id": instance_id,
            "workstream_id": workstream_id,
        }
        for case_id, instance_id, workstream_id in sorted(
            all_workstream_keys - accepted_workstream_keys
        )
    ]
    return {
        "audit_version": 1,
        "run_root": str(root.resolve()),
        "episode_count": len(episodes),
        "rejections": {
            "accepted_count": sum(outcome["outcome"] == "accepted" for outcome in outcomes),
            "rejected_count": sum(outcome["outcome"] == "rejected" for outcome in outcomes),
            "public_reason_counts": dict(sorted(public_reason_counts.items())),
            "private_reason_counts": dict(sorted(private_reason_counts.items())),
            "root_cause_counts": dict(sorted(root_cause_counts.items())),
            "publicly_actionable_rejection_count": sum(outcome["publicly_actionable"] for outcome in outcomes),
            "rejections_with_public_structural_reason_count": sum(
                outcome["has_public_structural_reason"] for outcome in outcomes
            ),
            "private_validator_review_rejection_count": sum(
                outcome["requires_private_validator_review"] for outcome in outcomes
            ),
            "per_workstream": per_workstream,
            "outcomes": outcomes,
        },
        "resources": {
            "total_tokens": int(sum(tokens)),
            "max_episode_tokens": int(max(tokens, default=0)),
            "p95_episode_tokens": int(_percentile(tokens, 0.95) or 0),
            "total_duration_ms": sum(durations),
            "max_episode_duration_ms": max(durations, default=0.0),
            "p95_episode_duration_ms": _percentile(durations, 0.95) or 0.0,
            "main_turn_limit_reached_count": sum(item["main_turn_limit_reached"] for item in episodes),
            "child_turn_limit_hit_count": sum(len(item["child_turn_limit_hit_ids"]) for item in episodes),
            "child_budget_exhausted_count": sum(len(item["child_budget_exhausted_ids"]) for item in episodes),
            "budget_exhausted_episode_count": sum(item["budget_exhausted"] for item in episodes),
            "episodes": episodes,
        },
        "contract_fixtures": fixtures,
        "validator_observation_coverage": {
            "workstream_count": len(all_workstream_keys),
            "workstreams_with_observed_acceptance": len(accepted_workstream_keys),
            "coverage": (
                len(accepted_workstream_keys) / len(all_workstream_keys)
                if all_workstream_keys else 0.0
            ),
            "missing_positive_observation": missing_positive_observation,
            "note": (
                "Observed acceptance is empirical pilot evidence, not an oracle proof. "
                "Missing workstreams require the next official regression or an "
                "executable case-owned positive fixture."
            ),
        },
        "artifact_compatibility": {
            "all_episodes_match_current": all(
                item["case_contract_matches_current"]
                and item["scaffold_matches_current"]
                and item["evaluation_contract_matches_current"]
                for item in episodes
            ) if episodes else False,
            "case_contract_match_count": sum(
                item["case_contract_matches_current"] for item in episodes
            ),
            "scaffold_match_count": sum(item["scaffold_matches_current"] for item in episodes),
            "evaluation_contract_match_count": sum(
                item["evaluation_contract_matches_current"] for item in episodes
            ),
            "note": (
                "A mismatched run is valid historical diagnostic evidence only and "
                "cannot certify the current benchmark revision."
            ),
        },
        "child_terminal_integrity": {
            "episodes_with_private_only_rejection": private_only_episode_ids,
            "episodes_with_unknown_child_terminal": unknown_terminal_episode_ids,
            "official_linear_zero_main_episode_ids": official_linear_zero_main_episode_ids,
            "note": (
                "Each spawned child must reach exactly one concrete terminal once "
                "its episode closes; a private-only rejection and an in-flight "
                "close are mechanism defects, never model submission verdicts."
            ),
        },
        "hard_fail": bool(hard_fail_reasons),
        "hard_fail_reasons": hard_fail_reasons,
    }
