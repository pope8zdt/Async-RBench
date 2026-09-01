"""Low-cost Terminal-Bench trajectory curation and fixed-choice review forms."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DEFAULT_MANIFEST = (
    "https://huggingface.co/datasets/Contextbench/Tracebench/resolve/main/"
    "bench_manifest.full.jsonl"
)
DEFAULT_ARTIFACT_BASE = (
    "https://huggingface.co/datasets/Contextbench/Tracebench/resolve/main/"
)

AUTHORITATIVE_SOURCE_CATALOG = {
    "terminal_bench": {
        "benchmark": "Terminal-Bench",
        "official_url": "https://github.com/laude-institute/terminal-bench-leaderboard",
        "trajectory_status": "public_execution_logs",
    },
    "swe_bench": {
        "benchmark": "SWE-bench",
        "official_url": "https://github.com/SWE-bench/experiments",
        "trajectory_status": "public_execution_logs",
    },
}

CHOICES = {
    "yes_no_uncertain": ("pending", "yes", "no", "uncertain"),
    "trajectory_quality": ("pending", "usable", "partial", "unusable"),
    "failure_attribution": (
        "pending", "model", "benchmark", "infrastructure", "not_failure", "uncertain",
    ),
    "version_match": ("pending", "exact", "instruction_only", "mismatch", "unknown"),
    "review_decision": ("pending", "accept", "revise", "reject"),
    "replanning_evidence": ("pending", "direct", "indirect", "none", "uncertain"),
    "affected_scope": ("pending", "local_branch", "multiple_branches", "global", "none", "uncertain"),
    "capability_target": (
        "pending", "base_task_completion", "async_result_integration",
        "async_dynamic_replanning", "async_consistency_closure",
    ),
    "relevance_tier": ("pending", "base", "supporting", "direct", "critical"),
    "research_events": (
        "late_authoritative_result", "conflicting_results", "stale_result_risk",
        "downstream_invalidation", "selective_preservation", "cancellation",
        "redelegation", "reverification", "no_research_event",
    ),
    "recommended_uses": (
        "positive_pattern", "failure_pattern", "counterfactual_source",
        "topology_source", "test_point_source", "ignore",
    ),
    "topology_roles": (
        "independent_parallel", "authority_producer", "provisional_producer",
        "downstream_consumer", "validation_branch", "recovery_branch",
    ),
}


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        if text[0] in "[{":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return default
    return value


def read_jsonl(source: str | Path) -> list[dict[str, Any]]:
    """Read a local path or HTTP(S) JSONL source without third-party dependencies."""
    source_text = str(source)
    if urllib.parse.urlparse(source_text).scheme in {"http", "https"}:
        with urllib.request.urlopen(source_text, timeout=60) as response:  # noqa: S310
            text = response.read().decode("utf-8")
    else:
        text = Path(source_text).read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    # JSON strings may legally contain U+2028/U+2029.  ``splitlines`` treats
    # those characters as record separators even though JSONL only uses the
    # physical LF delimiter, corrupting browser/GUI trajectory payloads.
    for line_number, raw_line in enumerate(text.split("\n"), 1):
        if not raw_line.strip():
            continue
        value = json.loads(raw_line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL line {line_number} must be an object")
        rows.append(value)
    return rows


def locked_task_ids(task_root: Path) -> list[str]:
    return sorted(
        path.name for path in task_root.iterdir()
        if path.is_dir() and (path / "task.yaml").is_file()
    )


def _rank(row: dict[str, Any]) -> tuple[int, int, str]:
    artifact = int(bool(row.get("artifact_path")))
    steps = int(row.get("step_count") or 0)
    return artifact, steps, str(row.get("traj_id") or row.get("trial_name") or "")


def select_trajectories(
    rows: Iterable[dict[str, Any]], task_ids: Iterable[str], per_task: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Select success/failure and agent-diverse traces deterministically."""
    if per_task < 1:
        raise ValueError("per_task must be positive")
    selected: list[dict[str, Any]] = []
    coverage: dict[str, int] = {}
    all_rows = list(rows)
    for task_id in sorted(set(task_ids)):
        candidates = [row for row in all_rows if str(row.get("task_name")) == task_id]
        coverage[task_id] = len(candidates)
        chosen: list[dict[str, Any]] = []

        def add_best(pool: Iterable[dict[str, Any]]) -> None:
            available = [row for row in pool if row not in chosen]
            if available and len(chosen) < per_task:
                chosen.append(max(available, key=_rank))

        add_best(row for row in candidates if row.get("solved") is True)
        add_best(row for row in candidates if row.get("solved") is False)
        while len(chosen) < per_task:
            used_agents = {str(row.get("agent")) for row in chosen}
            diverse = [
                row for row in candidates
                if row not in chosen and str(row.get("agent")) not in used_agents
            ]
            pool = diverse or [row for row in candidates if row not in chosen]
            if not pool:
                break
            add_best(pool)
        for row in chosen:
            copy = dict(row)
            copy["selection_reasons"] = _selection_reasons(copy, chosen)
            selected.append(copy)
    return selected, coverage


def authoritative_source_key(row: dict[str, Any]) -> str:
    """Classify a TraceBench row by the benchmark that produced the execution."""
    relpath = str(row.get("source_relpath") or "")
    return "swe_bench" if relpath.startswith("swe_raw/") else "terminal_bench"


def _campaign_rank(row: dict[str, Any]) -> tuple[int, int, int, int, str]:
    """Prefer auditable, substantive trajectories with localized error evidence."""
    steps = int(row.get("step_count") or 0)
    incorrect = int(row.get("incorrect_error_stage_count") or 0)
    stages = int(row.get("stage_count") or 0)
    substantive = int(12 <= steps <= 240)
    return (
        int(bool(row.get("artifact_path"))),
        int(incorrect > 0),
        substantive,
        min(steps, 240) + min(stages, 20) * 4 + min(incorrect, 5) * 20,
        str(row.get("traj_id") or row.get("trial_name") or ""),
    )


def _round_robin_strata(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Take rows across agent/model/category strata without randomness."""
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("agent") or "unknown"),
            str(row.get("model") or "unknown"),
            str(row.get("category") or "unknown"),
        )
        buckets.setdefault(key, []).append(row)
    for values in buckets.values():
        values.sort(key=_campaign_rank, reverse=True)
    selected: list[dict[str, Any]] = []
    keys = sorted(buckets)
    while len(selected) < limit and keys:
        next_keys: list[tuple[str, str, str]] = []
        for key in keys:
            if len(selected) == limit:
                break
            bucket = buckets[key]
            if bucket:
                selected.append(bucket.pop(0))
            if bucket:
                next_keys.append(key)
        keys = next_keys
    return selected


def select_authoritative_batch(
    rows: Iterable[dict[str, Any]], *, source_quotas: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select one authentic execution per task with source/outcome diversity.

    The input is the public TraceBench manifest. TraceBench is treated as an
    archive/distribution layer; every selected record retains the originating
    benchmark and its official log repository separately.
    """
    all_rows = list(rows)
    selected: list[dict[str, Any]] = []
    source_report: dict[str, Any] = {}
    for source_key, quota in source_quotas.items():
        if source_key not in AUTHORITATIVE_SOURCE_CATALOG:
            raise ValueError(f"unknown authoritative source: {source_key}")
        if quota < 1:
            raise ValueError("source quotas must be positive")
        eligible = [
            row for row in all_rows
            if authoritative_source_key(row) == source_key
            and bool(row.get("artifact_path"))
            and int(row.get("step_count") or 0) >= 6
        ]
        best_by_task_outcome: dict[tuple[str, bool | None], dict[str, Any]] = {}
        for row in eligible:
            task = str(row.get("task_name") or "")
            if not task:
                continue
            outcome = row.get("solved") if isinstance(row.get("solved"), bool) else None
            key = (task, outcome)
            current = best_by_task_outcome.get(key)
            if current is None or _campaign_rank(row) > _campaign_rank(current):
                best_by_task_outcome[key] = row
        unique_tasks = {task for task, _ in best_by_task_outcome}
        candidates = list(best_by_task_outcome.values())
        if len(unique_tasks) < quota:
            raise ValueError(
                f"{source_key} has only {len(unique_tasks)} unique eligible tasks for quota {quota}"
            )
        solved_target = quota // 2
        task_outcomes: dict[str, set[bool | None]] = {}
        for task, outcome in best_by_task_outcome:
            task_outcomes.setdefault(task, set()).add(outcome)
        solved_only = [
            row for row in candidates
            if row.get("solved") is True
            and False not in task_outcomes[str(row.get("task_name") or "")]
        ]
        solved_both = [
            row for row in candidates
            if row.get("solved") is True and row not in solved_only
        ]
        solved = _round_robin_strata(solved_only, solved_target)
        selected_tasks = {str(row.get("task_name") or "") for row in solved}
        if len(solved) < solved_target:
            solved.extend(_round_robin_strata(
                [row for row in solved_both if str(row.get("task_name") or "") not in selected_tasks],
                solved_target - len(solved),
            ))
        selected_tasks = {str(row.get("task_name") or "") for row in solved}
        unsolved_target = quota - len(solved)
        unsolved = _round_robin_strata([
            row for row in candidates
            if row.get("solved") is False
            and str(row.get("task_name") or "") not in selected_tasks
        ], unsolved_target)
        chosen = solved + unsolved
        if len(chosen) < quota:
            chosen_tasks = {str(row.get("task_name") or "") for row in chosen}
            remainder = [
                row for row in candidates
                if str(row.get("task_name") or "") not in chosen_tasks
            ]
            chosen.extend(_round_robin_strata(remainder, quota - len(chosen)))
        chosen.sort(key=lambda row: str(row.get("traj_id") or ""))
        catalog = AUTHORITATIVE_SOURCE_CATALOG[source_key]
        for row in chosen:
            copy = dict(row)
            copy.update({
                "benchmark_source_key": source_key,
                "benchmark": catalog["benchmark"],
                "official_source_url": catalog["official_url"],
                "archive_distribution_url": DEFAULT_ARTIFACT_BASE,
                "selection_reasons": _selection_reasons(copy, chosen) + [
                    "unique_task", "authoritative_execution_log",
                ],
            })
            selected.append(copy)
        source_report[source_key] = {
            "manifest_rows": len(eligible),
            "unique_eligible_tasks": len(unique_tasks),
            "selected": len(chosen),
            "solved": sum(row.get("solved") is True for row in chosen),
            "unsolved": sum(row.get("solved") is False for row in chosen),
        }
    selected.sort(key=lambda row: (
        str(row.get("benchmark_source_key") or ""), str(row.get("traj_id") or ""),
    ))
    if len({str(row.get("task_name") or "") for row in selected}) != len(selected):
        raise ValueError("authoritative batch contains duplicate task ids across sources")
    report = {
        "target_count": sum(source_quotas.values()),
        "selected_count": len(selected),
        "source_quotas": source_quotas,
        "sources": source_report,
        "unique_task_count": len({str(row.get("task_name") or "") for row in selected}),
        "unique_trajectory_count": len({str(row.get("traj_id") or "") for row in selected}),
    }
    return selected, report


def _diverse_task_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order repeated runs of one task by outcome, agent, and model novelty."""
    remaining = list(rows)
    ordered: list[dict[str, Any]] = []
    agents: set[str] = set()
    models: set[str] = set()
    outcomes: set[bool | None] = set()
    while remaining:
        def score(row: dict[str, Any]) -> tuple[Any, ...]:
            outcome = row.get("solved") if isinstance(row.get("solved"), bool) else None
            return (
                int(outcome not in outcomes),
                int(str(row.get("agent") or "") not in agents),
                int(str(row.get("model") or "") not in models),
                *_campaign_rank(row),
            )

        chosen = max(remaining, key=score)
        remaining.remove(chosen)
        ordered.append(chosen)
        agents.add(str(chosen.get("agent") or ""))
        models.add(str(chosen.get("model") or ""))
        outcomes.add(chosen.get("solved") if isinstance(chosen.get("solved"), bool) else None)
    return ordered


def select_authoritative_trajectory_batch(
    rows: Iterable[dict[str, Any]], *, source_quotas: dict[str, int],
    seed_ids: Iterable[str] = (), excluded_ids: Iterable[str] = (),
    max_per_task: int = 11,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a large run-level batch while bounding repeats of each task.

    Unlike :func:`select_authoritative_batch`, this expansion intentionally
    retains independent executions of the same task.  Seeds are included first;
    remaining slots are filled round-robin across tasks, with each task's runs
    ordered for agent/model/outcome diversity.
    """
    if max_per_task < 1:
        raise ValueError("max_per_task must be positive")
    all_rows = list(rows)
    seed_set, excluded_set = set(seed_ids), set(excluded_ids)
    selected: list[dict[str, Any]] = []
    source_report: dict[str, Any] = {}
    for source_key, quota in source_quotas.items():
        if source_key not in AUTHORITATIVE_SOURCE_CATALOG:
            raise ValueError(f"unknown authoritative source: {source_key}")
        eligible = [
            row for row in all_rows
            if authoritative_source_key(row) == source_key
            and bool(row.get("artifact_path"))
            and int(row.get("step_count") or 0) >= 6
            and str(row.get("traj_id") or "") not in excluded_set
        ]
        by_task: dict[str, list[dict[str, Any]]] = {}
        for row in eligible:
            task = str(row.get("task_name") or "")
            if task:
                by_task.setdefault(task, []).append(row)
        capacity = sum(min(len(values), max_per_task) for values in by_task.values())
        if quota > capacity:
            raise ValueError(
                f"{source_key} quota {quota} exceeds capped capacity {capacity}"
            )
        chosen: list[dict[str, Any]] = []
        chosen_ids: set[str] = set()
        task_counts: dict[str, int] = {}
        seeds = sorted(
            (row for row in eligible if str(row.get("traj_id") or "") in seed_set),
            key=lambda row: str(row.get("traj_id") or ""),
        )
        for row in seeds:
            task = str(row.get("task_name") or "")
            if task_counts.get(task, 0) >= max_per_task or len(chosen) >= quota:
                continue
            chosen.append(row)
            chosen_ids.add(str(row.get("traj_id") or ""))
            task_counts[task] = task_counts.get(task, 0) + 1
        buckets = {
            task: _diverse_task_order([
                row for row in values
                if str(row.get("traj_id") or "") not in chosen_ids
            ])
            for task, values in by_task.items()
        }
        task_keys = sorted(buckets)
        while len(chosen) < quota and task_keys:
            next_keys: list[str] = []
            for task in task_keys:
                if len(chosen) >= quota:
                    break
                bucket = buckets[task]
                if task_counts.get(task, 0) < max_per_task and bucket:
                    row = bucket.pop(0)
                    chosen.append(row)
                    chosen_ids.add(str(row.get("traj_id") or ""))
                    task_counts[task] = task_counts.get(task, 0) + 1
                if bucket and task_counts.get(task, 0) < max_per_task:
                    next_keys.append(task)
            task_keys = next_keys
        if len(chosen) != quota:
            raise ValueError(f"{source_key} selected {len(chosen)} of required {quota}")
        catalog = AUTHORITATIVE_SOURCE_CATALOG[source_key]
        for row in chosen:
            copy = dict(row)
            traj_id = str(copy.get("traj_id") or "")
            copy.update({
                "benchmark_source_key": source_key,
                "benchmark": catalog["benchmark"],
                "official_source_url": catalog["official_url"],
                "archive_distribution_url": DEFAULT_ARTIFACT_BASE,
                "selection_reasons": _selection_reasons(copy, chosen) + [
                    "seed_350" if traj_id in seed_set else "run_level_expansion",
                    "authoritative_execution_log", "task_repeat_bounded",
                ],
            })
            selected.append(copy)
        source_report[source_key] = {
            "manifest_rows": len(eligible), "unique_eligible_tasks": len(by_task),
            "capped_capacity": capacity, "selected": len(chosen),
            "seed_count": sum(str(row.get("traj_id") or "") in seed_set for row in chosen),
            "unique_selected_tasks": len({str(row.get("task_name") or "") for row in chosen}),
            "max_selected_per_task": max(Counter(str(row.get("task_name") or "") for row in chosen).values()),
            "solved": sum(row.get("solved") is True for row in chosen),
            "unsolved": sum(row.get("solved") is False for row in chosen),
        }
    selected.sort(key=lambda row: (
        str(row.get("benchmark_source_key") or ""), str(row.get("traj_id") or ""),
    ))
    ids = [str(row.get("traj_id") or "") for row in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("expanded batch contains duplicate trajectory ids")
    report = {
        "target_count": sum(source_quotas.values()), "selected_count": len(selected),
        "source_quotas": source_quotas, "max_per_task": max_per_task,
        "sources": source_report,
        "unique_task_count": len({str(row.get("task_name") or "") for row in selected}),
        "unique_trajectory_count": len(set(ids)),
        "seed_requested": len(seed_set), "seed_retained": sum(item in seed_set for item in ids),
        "excluded_count": len(excluded_set),
    }
    return selected, report


def _selection_reasons(row: dict[str, Any], chosen: list[dict[str, Any]]) -> list[str]:
    outcome_reason = (
        "manifest_solved" if row.get("solved") is True
        else "manifest_unsolved" if row.get("solved") is False
        else "manifest_outcome_unknown"
    )
    reasons = [outcome_reason]
    if sum(str(item.get("agent")) == str(row.get("agent")) for item in chosen) == 1:
        reasons.append("agent_diversity")
    if row.get("artifact_path"):
        reasons.append("raw_artifact_available")
    if int(row.get("step_count") or 0) >= 20:
        reasons.append("substantive_step_count")
    if _json_value(row.get("incorrect_stages"), []):
        reasons.append("contains_incorrect_stage_labels")
    return reasons


def trajectory_review_record(row: dict[str, Any]) -> dict[str, Any]:
    review_id = str(row.get("traj_id") or row.get("trial_name") or "")
    return {
        "review_id": review_id,
        "task_name": str(row.get("task_name") or ""),
        "source": {
            "agent": row.get("agent"), "model": row.get("model"),
            "trial_name": row.get("trial_name"), "artifact_path": row.get("artifact_path"),
            "source_relpath": row.get("source_relpath"),
            "benchmark": row.get("benchmark"),
            "benchmark_source_key": row.get("benchmark_source_key"),
            "official_source_url": row.get("official_source_url"),
            "archive_distribution_url": row.get("archive_distribution_url"),
        },
        "machine_screen": {
            "manifest_solved": row.get("solved"),
            "step_count": int(row.get("step_count") or 0),
            "stage_count": int(row.get("stage_count") or 0),
            "selection_reasons": list(row.get("selection_reasons") or []),
        },
        "agent_coarse_label": {
            "status": "pending",
            "trajectory_quality": "pending",
            "failure_attribution": "pending",
            "replanning_evidence": "pending",
            "research_events": [],
            "candidate_decision_count": 0,
            "evidence_step_ids": [],
        },
        "human_review": {
            "review_decision": "pending",
            "task_match": "pending",
            "version_match": "pending",
            "trajectory_quality": "pending",
            "failure_attribution": "pending",
            "replanning_evidence": "pending",
            "research_events": [],
            "recommended_uses": [],
            "evidence_step_ids": [],
            "reviewer_note": "",
        },
    }


def decision_review_template() -> dict[str, Any]:
    """Template filled first by a coarse-label agent and then by a human reviewer."""
    return {
        "decision_id": "",
        "trajectory_review_id": "",
        "task_name": "",
        "agent_proposal": {
            "event_type": "",
            "trigger_step_ids": [],
            "precondition_step_ids": [],
            "response_step_ids": [],
            "consequence_step_ids": [],
            "affected_step_ids": [],
            "affected_scope": "pending",
            "suggested_topology_roles": [],
            "suggested_capability_target": "pending",
            "suggested_relevance_tier": "pending",
            "counterfactual_failure": "",
            "rationale": "",
        },
        "human_review": {
            "trigger_can_be_async_result": "pending",
            "arrival_order_matters": "pending",
            "plan_change_required": "pending",
            "affected_scope": "pending",
            "semantic_consequence_observable": "pending",
            "control_consequence_observable": "pending",
            "prompt_leakage_risk": "pending",
            "benchmark_eligible": "pending",
            "capability_target": "pending",
            "relevance_tier": "pending",
            "topology_roles": [],
            "evidence_step_ids": [],
            "reviewer_note": "",
        },
    }


def _choice_errors(value: Any, choices: tuple[str, ...], field: str) -> list[str]:
    return [] if value in choices else [f"{field} must be one of {list(choices)!r}"]


def _multi_choice_errors(value: Any, choices: tuple[str, ...], field: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{field} must be a list"]
    invalid = [item for item in value if item not in choices]
    return [f"{field} has invalid choices {invalid!r}"] if invalid else []


def validate_review(record: dict[str, Any], kind: str) -> list[str]:
    """Validate fixed-choice human labels and evidence requirements."""
    errors: list[str] = []
    review = record.get("human_review")
    if not isinstance(review, dict):
        return ["human_review must be an object"]
    if kind == "trajectory":
        fields = {
            "review_decision": "review_decision",
            "task_match": "yes_no_uncertain",
            "version_match": "version_match",
            "trajectory_quality": "trajectory_quality",
            "failure_attribution": "failure_attribution",
            "replanning_evidence": "replanning_evidence",
        }
        for field, catalog in fields.items():
            errors.extend(_choice_errors(review.get(field), CHOICES[catalog], field))
            if review.get(field) == "pending":
                errors.append(f"{field} is still pending")
        errors.extend(_multi_choice_errors(
            review.get("research_events"), CHOICES["research_events"], "research_events",
        ))
        errors.extend(_multi_choice_errors(
            review.get("recommended_uses"), CHOICES["recommended_uses"], "recommended_uses",
        ))
        if review.get("review_decision") == "accept" and not review.get("evidence_step_ids"):
            errors.append("accepted trajectory review requires evidence_step_ids")
        if review.get("review_decision") == "accept" and not review.get("research_events"):
            errors.append("accepted trajectory review requires at least one research event")
        if review.get("review_decision") == "accept" and not review.get("recommended_uses"):
            errors.append("accepted trajectory review requires at least one recommended use")
    elif kind == "decision":
        for field in (
            "trigger_can_be_async_result", "arrival_order_matters", "plan_change_required",
            "semantic_consequence_observable", "control_consequence_observable",
            "prompt_leakage_risk",
        ):
            errors.extend(_choice_errors(review.get(field), CHOICES["yes_no_uncertain"], field))
            if review.get(field) == "pending":
                errors.append(f"{field} is still pending")
        fields = {
            "affected_scope": "affected_scope", "benchmark_eligible": "review_decision",
            "capability_target": "capability_target", "relevance_tier": "relevance_tier",
        }
        for field, catalog in fields.items():
            errors.extend(_choice_errors(review.get(field), CHOICES[catalog], field))
            if review.get(field) == "pending":
                errors.append(f"{field} is still pending")
        errors.extend(_multi_choice_errors(
            review.get("topology_roles"), CHOICES["topology_roles"], "topology_roles",
        ))
        if review.get("benchmark_eligible") == "accept":
            if not review.get("evidence_step_ids"):
                errors.append("accepted decision point requires evidence_step_ids")
            if review.get("trigger_can_be_async_result") != "yes":
                errors.append("accepted decision point must be convertible to an async result")
            if review.get("arrival_order_matters") != "yes":
                errors.append("accepted decision point must depend on asynchronous arrival order")
            if review.get("plan_change_required") != "yes":
                errors.append("accepted decision point must require a plan change")
            if review.get("capability_target") == "base_task_completion":
                errors.append("accepted decision point cannot be only base task completion")
            if review.get("relevance_tier") in {"pending", "base"}:
                errors.append("accepted decision point must score above the base tier")
            if review.get("prompt_leakage_risk") != "no":
                errors.append("accepted decision point must not leak the intended answer")
            if not review.get("topology_roles"):
                errors.append("accepted decision point requires at least one topology role")
            if not (
                review.get("semantic_consequence_observable") == "yes"
                or review.get("control_consequence_observable") == "yes"
            ):
                errors.append("accepted decision point needs an observable semantic or control consequence")
    else:
        errors.append("kind must be 'trajectory' or 'decision'")
    return errors


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def download_artifacts(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        artifact_path = str((row.get("source") or {}).get("artifact_path") or "")
        if not artifact_path:
            continue
        filename = Path(artifact_path).name
        target = output_dir / filename
        url = urllib.parse.urljoin(
            DEFAULT_ARTIFACT_BASE, urllib.parse.quote(artifact_path, safe="/"),
        )
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
            payload = response.read()
        target.write_bytes(payload)
        row["source"]["local_artifact"] = str(target.resolve())
        row["source"]["artifact_sha256"] = hashlib.sha256(payload).hexdigest()


def render_review_html(records: list[dict[str, Any]], output: Path) -> None:
    """Render a no-server review page with dropdowns, checkboxes and JSON export."""
    payload = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    catalogs = json.dumps(CHOICES, ensure_ascii=False)
    page = _HTML_TEMPLATE.replace("__RECORDS__", payload).replace("__CHOICES__", catalogs)
    output.write_text(page, encoding="utf-8")


def render_decision_review_html(records: list[dict[str, Any]], output: Path) -> None:
    """Render decision-point review as judgments, dropdowns and checkboxes."""
    payload = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    catalogs = json.dumps(CHOICES, ensure_ascii=False)
    page = _DECISION_HTML_TEMPLATE.replace("__RECORDS__", payload).replace(
        "__CHOICES__", catalogs,
    )
    output.write_text(page, encoding="utf-8")


_HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Async-RBench 轨迹人工复核</title>
<style>
body{font:15px system-ui;margin:24px auto;max-width:1180px;color:#202124}h1{margin-bottom:6px}
.hint{color:#5f6368}.card{border:1px solid #dadce0;border-radius:10px;padding:18px;margin:18px 0}
.meta{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;background:#f8f9fa;padding:10px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}label{display:block}
select,input{width:100%;padding:7px;margin-top:4px}.checks label{display:inline-block;margin:6px 14px 0 0}
.checks input{width:auto}button{padding:10px 16px;margin-right:8px}.pending{border-left:5px solid #f9ab00}
@media(max-width:800px){.grid,.meta{grid-template-columns:1fr}}
</style></head><body><h1>Async-RBench 轨迹人工复核</h1>
<p class="hint">只需选择或判断；仅证据步骤编号与可选备注允许文本输入。结果只保存在浏览器内，点击导出下载 JSONL。</p>
<button onclick="exportJsonl()">导出复核 JSONL</button><span id="progress"></span><div id="root"></div>
<script>const records=__RECORDS__;const choices=__CHOICES__;
const fields=[['review_decision','review_decision'],['task_match','yes_no_uncertain'],['version_match','version_match'],['trajectory_quality','trajectory_quality'],['failure_attribution','failure_attribution'],['replanning_evidence','replanning_evidence']];
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function select(rec,field,cat){return `<label>${field}<select data-id="${esc(rec.review_id)}" data-field="${field}">${choices[cat].map(v=>`<option ${rec.human_review[field]===v?'selected':''}>${v}</option>`).join('')}</select></label>`}
function checks(rec,field,cat){return `<div class="checks"><b>${field}</b><br>${choices[cat].map(v=>`<label><input type="checkbox" data-id="${esc(rec.review_id)}" data-field="${field}" value="${v}" ${(rec.human_review[field]||[]).includes(v)?'checked':''}>${v}</label>`).join('')}</div>`}
function render(){root.innerHTML=records.map(r=>`<section class="card pending"><h2>${esc(r.task_name)}</h2><div class="meta"><span>${esc(r.source.agent)}</span><span>${esc(r.source.model)}</span><span>steps: ${r.machine_screen.step_count}</span><span>${esc(r.review_id)}</span></div><div class="grid">${fields.map(f=>select(r,...f)).join('')}</div>${checks(r,'research_events','research_events')}${checks(r,'recommended_uses','recommended_uses')}<div class="grid"><label>evidence_step_ids（逗号分隔）<input data-id="${esc(r.review_id)}" data-field="evidence_step_ids" value="${esc((r.human_review.evidence_step_ids||[]).join(','))}"></label><label>reviewer_note（可选）<input data-id="${esc(r.review_id)}" data-field="reviewer_note" value="${esc(r.human_review.reviewer_note)}"></label></div></section>`).join(''); bind();progress.textContent=`共 ${records.length} 条`}
function bind(){document.querySelectorAll('[data-field]').forEach(el=>el.onchange=()=>{const r=records.find(x=>x.review_id===el.dataset.id),f=el.dataset.field;if(el.type==='checkbox'){r.human_review[f]=[...document.querySelectorAll(`[data-id="${CSS.escape(el.dataset.id)}"][data-field="${f}"]:checked`)].map(x=>x.value)}else if(f==='evidence_step_ids'){r.human_review[f]=el.value.split(',').map(x=>x.trim()).filter(Boolean).map(Number).filter(Number.isFinite)}else r.human_review[f]=el.value})}
function exportJsonl(){const blob=new Blob([records.map(x=>JSON.stringify(x)).join('\n')+'\n'],{type:'application/jsonl'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='trajectory_reviews.completed.jsonl';a.click();URL.revokeObjectURL(a.href)}render();
</script></body></html>'''


_DECISION_HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Async-RBench 决策点复核</title>
<style>body{font:15px system-ui;margin:24px auto;max-width:1180px;color:#202124}.card{border:1px solid #dadce0;border-radius:10px;padding:18px;margin:18px 0}.meta{background:#f8f9fa;padding:10px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}label{display:block}select,input{width:100%;padding:7px;margin-top:4px}.checks label{display:inline-block;margin:6px 14px 0 0}.checks input{width:auto}button{padding:10px 16px}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style></head>
<body><h1>异步决策点人工复核</h1><p>先判断是否由异步结果触发、是否必须改计划，再选择能力和权重；接受时必须填写证据步骤。</p><button onclick="exportJsonl()">导出决策点 JSONL</button><div id="root"></div>
<script>const records=__RECORDS__;const choices=__CHOICES__;const yn=['trigger_can_be_async_result','arrival_order_matters','plan_change_required','semantic_consequence_observable','control_consequence_observable','prompt_leakage_risk'];const sels=[['affected_scope','affected_scope'],['benchmark_eligible','review_decision'],['capability_target','capability_target'],['relevance_tier','relevance_tier']];
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}function select(r,f,c){return `<label>${f}<select data-id="${esc(r.decision_id)}" data-field="${f}">${choices[c].map(v=>`<option ${r.human_review[f]===v?'selected':''}>${v}</option>`).join('')}</select></label>`}function checks(r){return `<div class="checks"><b>topology_roles</b><br>${choices.topology_roles.map(v=>`<label><input type="checkbox" data-id="${esc(r.decision_id)}" data-field="topology_roles" value="${v}" ${(r.human_review.topology_roles||[]).includes(v)?'checked':''}>${v}</label>`).join('')}</div>`}
function render(){root.innerHTML=records.map(r=>`<section class="card"><h2>${esc(r.task_name)} / ${esc(r.decision_id)}</h2><div class="meta">agent proposal: ${esc(r.agent_proposal.event_type)}; trigger steps: ${esc((r.agent_proposal.trigger_step_ids||[]).join(','))}</div><div class="grid">${yn.map(f=>select(r,f,'yes_no_uncertain')).join('')}${sels.map(f=>select(r,...f)).join('')}</div>${checks(r)}<div class="grid"><label>evidence_step_ids（逗号分隔）<input data-id="${esc(r.decision_id)}" data-field="evidence_step_ids" value="${esc((r.human_review.evidence_step_ids||[]).join(','))}"></label><label>reviewer_note（可选）<input data-id="${esc(r.decision_id)}" data-field="reviewer_note" value="${esc(r.human_review.reviewer_note)}"></label></div></section>`).join('');bind()}
function bind(){document.querySelectorAll('[data-field]').forEach(el=>el.onchange=()=>{const r=records.find(x=>x.decision_id===el.dataset.id),f=el.dataset.field;if(el.type==='checkbox'){r.human_review[f]=[...document.querySelectorAll(`[data-id="${CSS.escape(el.dataset.id)}"][data-field="${f}"]:checked`)].map(x=>x.value)}else if(f==='evidence_step_ids'){r.human_review[f]=el.value.split(',').map(x=>x.trim()).filter(Boolean).map(Number).filter(Number.isFinite)}else r.human_review[f]=el.value})}function exportJsonl(){const blob=new Blob([records.map(x=>JSON.stringify(x)).join('\n')+'\n'],{type:'application/jsonl'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='decision_reviews.completed.jsonl';a.click();URL.revokeObjectURL(a.href)}render();
</script></body></html>'''


def initialise_curation(
    *, root: Path, manifest: str, output: Path, per_task: int,
    fetch_artifacts: bool = False,
) -> dict[str, Any]:
    task_root = root / "upstream" / "terminal-bench" / "original-tasks-locked"
    tasks = locked_task_ids(task_root)
    rows = read_jsonl(manifest)
    selected, coverage = select_trajectories(rows, tasks, per_task=per_task)
    artifact_coverage = {
        task: sum(
            str(row.get("task_name")) == task and bool(row.get("artifact_path"))
            for row in rows
        )
        for task in tasks
    }
    output.mkdir(parents=True, exist_ok=True)
    reviews = [trajectory_review_record(row) for row in selected]
    if fetch_artifacts:
        download_artifacts(reviews, output / "raw_artifacts")
    write_jsonl(output / "trajectory_reviews.jsonl", reviews)
    (output / "decision_review.template.json").write_text(
        json.dumps(decision_review_template(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "choice_catalog.json").write_text(
        json.dumps(CHOICES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    render_review_html(reviews, output / "trajectory_review.html")
    summary = {
        "manifest": manifest, "locked_task_count": len(tasks),
        "selected_trajectory_count": len(reviews), "coverage": coverage,
        "artifact_coverage": artifact_coverage,
        "selected_with_artifact_count": sum(
            bool((review.get("source") or {}).get("artifact_path")) for review in reviews
        ),
        "missing_tasks": [task for task, count in coverage.items() if count == 0],
        "artifacts_downloaded": fetch_artifacts,
    }
    (output / "curation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return summary
