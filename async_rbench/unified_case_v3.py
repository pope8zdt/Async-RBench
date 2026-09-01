"""Normalization and deterministic audit helpers for the unified case inventory."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


FAMILIES = {
    "conflicting_specialist_results",
    "cross_app_artifact",
    "dependency_unblock",
    "late_constraint",
    "late_test_evidence",
    "partial_failure_recovery",
    "state_reconciliation",
}

PREFIXES = {
    "GAIA2": "gai",
    "SentinelBench": "sen",
    "Terminal-Bench": "tbn",
    "OSWorld": "osw",
    "SWE-bench": "swe",
    "MultiAgentBench": "mab",
}

GENERIC_AFFECTED_PATTERNS = (
    "the main branch starts",
    "the main branch begins",
    "the main branch implements",
    "the main agent continues",
    "downstream assembly, optimization, or reporting proceeds",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    # JSON strings may legitimately contain U+2028/U+2029 when ensure_ascii=False.
    # str.splitlines() treats those code points as record separators and corrupts
    # otherwise valid JSONL.  JSONL records here are delimited only by ASCII LF.
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").split("\n")
        if line.strip()
    ]


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def semantic_family(case: dict[str, Any]) -> str:
    family = str(case.get("family") or "")
    if family in FAMILIES:
        return family
    causal = case.get("causal_record") or {}
    event = causal.get("independent_event") or {}
    affected = causal.get("affected_work") or []
    text = " ".join([
        str(event.get("description") or ""),
        *(str(item.get("description") or "") for item in affected),
        str((case.get("source") or {}).get("instruction") or ""),
    ]).lower()
    apps = {str(item.get("app")) for item in affected if item.get("app")}
    if "conflict" in text or "disagree" in text:
        return "conflicting_specialist_results"
    if "test" in text or "reverif" in text or "validation" in text:
        return "late_test_evidence"
    if "failure" in text or "recover" in text or "retry" in text:
        return "partial_failure_recovery"
    if len(apps) > 1 or "spreadsheet" in text or "attachment" in text:
        return "cross_app_artifact"
    if "constraint" in text or "availability" in text or "deadline" in text:
        return "late_constraint"
    if "state" in text or "reconcile" in text:
        return "state_reconciliation"
    return "dependency_unblock"


def evidence_class(case: dict[str, Any], collection: str) -> str:
    source = case.get("source") or {}
    existing = source.get("evidence_class")
    if existing:
        return str(existing)
    kind = str(source.get("source_kind") or "")
    if kind in {"official_dynamic_event_graph", "official_dynamic_event_timeline"}:
        return "official_dynamic_event_trace"
    if collection == "legacy-300" and source.get("benchmark") == "Terminal-Bench":
        return "public_model_execution_trace_with_incomplete_provenance"
    return "unknown"


def stable_case_id(case: dict[str, Any], family: str) -> str:
    source = case.get("source") or {}
    benchmark = str(source.get("benchmark") or "unknown")
    prefix = PREFIXES.get(benchmark, "unk")
    identity = {
        "benchmark": benchmark,
        "task_id": source.get("task_id"),
        "instruction_sha256": source.get("instruction_sha256"),
    }
    return f"{prefix}-{family.replace('_', '-')}-{canonical_hash(identity)[:10]}"


def deterministic_issues(
    case: dict[str, Any], expected: dict[str, Any], collection: str
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def add(code: str, severity: str, detail: str) -> None:
        issues.append({"code": code, "severity": severity, "detail": detail})

    source = case.get("source") or {}
    causal = case.get("causal_record") or {}
    event = causal.get("independent_event") or {}
    instruction = str(source.get("instruction") or "").strip()
    event_text = str(event.get("description") or "").strip()
    prior = causal.get("prior_work") or []
    affected = causal.get("affected_work") or []
    stale = causal.get("superseded_work") or []

    if not instruction:
        add("empty_instruction", "fatal", "The authoritative task instruction is empty.")
    if instruction.endswith("…") or instruction.endswith("..."):
        add("truncated_instruction", "major", "The stored source instruction appears truncated.")
    if not source.get("source_kind") or not source.get("source_url"):
        add("incomplete_source_provenance", "major", "Source kind or URL is missing.")
    if not prior:
        add("missing_prior_work", "fatal", "No pre-event work is represented.")
    if not affected:
        add("missing_affected_work", "fatal", "No causally affected work is represented.")
    if not event_text:
        add("empty_event", "fatal", "The asynchronous event has no payload.")
    if re.fullmatch(r"[a-z_ -]{3,40}", event_text.lower()):
        add("underspecified_event_payload", "major", "The event is only a categorical label, not task evidence.")
    if str(event.get("kind") or "").lower() == "action" and any(
        token in event_text.lower() for token in ("i am thinking", "let me verify", "i have ")
    ):
        add("non_independent_event", "fatal", "The alleged event is the focal model's own action or reasoning.")
    affected_texts = [str(item.get("description") or "").strip() for item in affected]
    if any(any(text.lower().startswith(pattern) for pattern in GENERIC_AFFECTED_PATTERNS) for text in affected_texts):
        add("generic_affected_work", "major", "Affected work is a reusable template rather than task-specific behavior.")
    prior_text = " ".join(str(item.get("description") or "") for item in prior).lower()
    if any(token in prior_text for token in ("missing required parameters", "warning>", "traceback")):
        add("invalid_prior_work", "major", "Prior work is an error/diagnostic rather than valid work to preserve.")
    if not stale and expected.get("superseded_work_ids"):
        add("private_only_stale_work", "major", "Stale work exists only in private expected data.")
    if collection == "legacy-300":
        add("legacy_async_specific_scoring", "major", "The original eight-point rubric mixes async process with outcome score.")
        add("weak_review_independence", "major", "Legacy stage labels are not independent reviewer judgments.")
    else:
        add("source_native_replay_missing", "major", "The capsule scores symbolic actions rather than the source-native environment.")
        add("collection_challenge_gate_failed", "major", "The collection-level pilot did not show Async below Linear.")
    weights = [float(item.get("weight") or 0) for item in case.get("score_points") or []]
    if not weights or abs(sum(weights) - 1.0) > 1e-6:
        add("invalid_score_weights", "fatal", "Score-point weights are absent or do not sum to one.")
    return issues


def compact_review_record(
    case: dict[str, Any], expected: dict[str, Any], collection: str, path: str
) -> dict[str, Any]:
    family = semantic_family(case)
    issues = deterministic_issues(case, expected, collection)
    source = case.get("source") or {}
    causal = case.get("causal_record") or {}
    return {
        "unified_candidate_id": stable_case_id(case, family),
        "collection": collection,
        "original_case_id": case.get("case_id"),
        "original_schema_version": case.get("schema_version"),
        "source_path": path,
        "benchmark": source.get("benchmark"),
        "source_task_id": source.get("task_id"),
        "evidence_class": evidence_class(case, collection),
        "current_family": family,
        "instruction": str(source.get("instruction") or ""),
        "prior_work": causal.get("prior_work") or [],
        "independent_event": causal.get("independent_event") or {},
        "affected_work": causal.get("affected_work") or [],
        "superseded_work": causal.get("superseded_work") or [],
        "expected_superseded_work_ids": expected.get("superseded_work_ids") or [],
        "deterministic_issues": issues,
        "fatal_issue_count": sum(item["severity"] == "fatal" for item in issues),
        "major_issue_count": sum(item["severity"] == "major" for item in issues),
    }
