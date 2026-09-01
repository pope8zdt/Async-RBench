from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from .case_contract import PUBLIC_RESULT_REJECTION_CODES
from .protocol import load_trace
from .result_contract import validate_payload_contract
from ..spec import case_instance_key, discover_case_instances


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
    return {
        "type": "child_completed",
        "payload": {
            "summary": "contract audit fixture",
            "evidence": evidence,
            "files": list(workstream.get("required_files") or []),
        },
    }


def audit_contract_fixtures(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for instance in discover_case_instances(root):
        case = instance.load()
        sufficiency = {
            str(item.get("workstream_id")): item
            for item in case.raw.get("information_sufficiency") or []
        }
        for workstream in case.raw.get("delegation_workstreams") or []:
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
            passed = bool(
                not positive_codes
                and expected_negative_code in negative_codes
                and schema_names_match
                and public_types_match
                and sufficiency_matches
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
                "passed": passed,
            }
            rows.append(row)
            if not passed:
                failures.append(f"{case.case_id}/{instance.instance_id}/{stream_id}")
    return {
        "workstream_count": len(rows),
        "passed_count": sum(bool(row["passed"]) for row in rows),
        "failed_workstreams": failures,
        "passed": not failures,
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


def audit_run(root: Path, benchmark_root: Path) -> dict[str, Any]:
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
    fixtures = audit_contract_fixtures(benchmark_root)
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
    }
