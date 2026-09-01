"""Task-level transformability audit for the 607 generated case records.

This module answers a different question from publication readiness: whether a
source task contains enough authoritative task truth and causal structure to be
rebuilt into a complete Async-RBench task. Missing runtime infrastructure is a
reconstruction cost, not an automatic rejection.
"""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .case_ir import compile_score_plan, validate_case_ir, validate_score_plan


THEME_CAPABILITIES = {
    "delayed_authoritative_result": [
        "late_revision_adoption", "selective_invalidation", "verification_reopen",
    ],
    "late_or_out_of_order_superseded_result": [
        "stale_result_rejection", "selective_invalidation", "verification_reopen",
    ],
    "partial_then_complete_result": [
        "late_revision_adoption", "selective_invalidation", "verification_reopen",
    ],
    "conflicting_valid_results": [
        "conflict_arbitration", "selective_invalidation", "verification_reopen",
    ],
    "duplicate_or_replayed_completion": [
        "stale_result_rejection", "selective_invalidation",
    ],
    "child_failure_or_implicit_error": [
        "failure_redelegation", "cascading_replan", "verification_reopen",
    ],
    "task_scope_or_dependency_change": [
        "late_revision_adoption", "selective_invalidation", "cascading_replan",
        "verification_reopen",
    ],
    "straggler_under_resource_pressure": [
        "inflight_cancellation", "cascading_replan", "verification_reopen",
    ],
}

THEME_DECISIONS = {
    "delayed_authoritative_result": [
        ("classify_authority", "event_intake", "ignore_authority", "wait_for_authority"),
        ("revise_affected", "state_revision", "retain_provisional", "resolve_authority"),
        ("verify_closure", "closure", "skip_reverification", "rederive_from_authority"),
    ],
    "late_or_out_of_order_superseded_result": [
        ("classify_stale", "event_intake", "accept_stale", "reject_late_stale"),
        ("exclude_stale", "state_revision", "rollback_to_stale", "reject_late_stale"),
        ("verify_closure", "closure", "mix_lineages", "rederive_from_authority"),
    ],
    "partial_then_complete_result": [
        ("classify_completeness", "event_intake", "treat_partial_as_final", "wait_for_authority"),
        ("revise_affected", "state_revision", "drop_confirmed_partial", "resolve_authority"),
        ("verify_closure", "closure", "skip_reverification", "rederive_from_authority"),
    ],
    "conflicting_valid_results": [
        ("classify_conflict", "event_intake", "blind_first_result", "arbitrate_conflict"),
        ("arbitrate_conflict", "state_revision", "blind_last_result", "arbitrate_conflict"),
        ("verify_closure", "closure", "inconsistent_merge", "rederive_from_authority"),
    ],
    "duplicate_or_replayed_completion": [
        ("classify_duplicate", "event_intake", "double_consume", "deduplicate_completion"),
        ("preserve_idempotency", "state_revision", "duplicate_side_effect", "deduplicate_completion"),
    ],
    "child_failure_or_implicit_error": [
        ("classify_failure", "event_intake", "promote_failed_result", "recover_failed_work"),
        ("recover_or_redelegate", "plan_revision", "omit_recovery", "recover_failed_work"),
        ("verify_closure", "closure", "false_success", "rederive_from_authority"),
    ],
    "task_scope_or_dependency_change": [
        ("classify_scope_delta", "event_intake", "ignore_new_requirement", "wait_for_authority"),
        ("revise_affected", "state_revision", "under_invalidate", "resolve_authority"),
        ("preserve_unaffected", "plan_revision", "over_invalidate", "selective_replan"),
        ("verify_closure", "closure", "skip_reverification", "rederive_from_authority"),
    ],
    "straggler_under_resource_pressure": [
        ("classify_critical_path", "event_intake", "wait_for_low_value_straggler", "resource_triage"),
        ("resource_triage", "plan_revision", "cancel_critical_work", "resource_triage"),
        ("verify_closure", "closure", "exceed_budget", "rederive_from_authority"),
    ],
}

TB_COMPOSITIONS = {
    "multi-source-data-merger": (
        "data-recovery-composite-v2",
        ["multi-source-data-merger", "db-wal-recovery"],
        "Recovered database rows feed the multi-source normalization and conflict-resolution stage.",
    ),
    "db-wal-recovery": (
        "data-recovery-composite-v2",
        ["multi-source-data-merger", "db-wal-recovery"],
        "Recovered database rows feed the multi-source normalization and conflict-resolution stage.",
    ),
    "nginx-request-logging": (
        "secure-release-composite-v2",
        ["fix-code-vulnerability", "git-leak-recovery", "nginx-request-logging"],
        "The repaired source and sanitized history become the deployable Nginx release, which is reverified live.",
    ),
    "fix-code-vulnerability": (
        "secure-release-composite-v2",
        ["fix-code-vulnerability", "git-leak-recovery", "nginx-request-logging"],
        "The repaired source and sanitized history become the deployable Nginx release, which is reverified live.",
    ),
    "git-leak-recovery": (
        "secure-release-composite-v2",
        ["fix-code-vulnerability", "git-leak-recovery", "nginx-request-logging"],
        "The repaired source and sanitized history become the deployable Nginx release, which is reverified live.",
    ),
    "llm-inference-batching-scheduler": (
        "distributed-runtime-scheduler-v2",
        ["llm-inference-batching-scheduler"],
        "One deep upstream task is decomposed into profiling, planning, runtime realization and closure verification.",
    ),
}

# A constructive allocation proving that the technically transformable pool can
# satisfy the pre-calibration 450-task event/scenario margins after source-policy
# resolution. Keys are primary event themes; values are scenario-class counts.
BALANCED_450_ALLOCATION = {
    "delayed_authoritative_result": {"live_eventful": 6, "resource_eventful": 2, "result_eventful": 49},
    "late_or_out_of_order_superseded_result": {"result_eventful": 57},
    "partial_then_complete_result": {"live_eventful": 1, "resource_eventful": 7, "result_eventful": 48},
    "conflicting_valid_results": {"live_eventful": 56},
    "duplicate_or_replayed_completion": {"live_eventful": 28, "result_eventful": 28},
    "child_failure_or_implicit_error": {"resource_eventful": 25, "result_eventful": 31},
    "task_scope_or_dependency_change": {"live_eventful": 44, "result_eventful": 12},
    "straggler_under_resource_pressure": {"resource_eventful": 56},
}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _slug(value: str, limit: int = 52) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return (value or "item")[:limit]


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _source_instruction(native_dir: Path, benchmark: str, production_case: dict[str, Any]) -> str:
    participant = _json(native_dir / "participant_task.json")
    if benchmark == "MultiAgentBench":
        task = participant.get("task") or {}
        return "\n".join(filter(None, [str(task.get("content") or ""), str(task.get("output_format") or "")]))
    if benchmark == "OSWorld":
        return str(participant.get("instruction") or "")
    if benchmark == "SWE-bench":
        return str(participant.get("problem_statement") or "")
    return str((production_case.get("source") or {}).get("instruction") or "")


def _causal_text(causal: dict[str, Any]) -> str:
    parts = [causal.get("async_stressor"), (causal.get("independent_event") or {}).get("description")]
    for field in ("prior_work", "affected_work", "superseded_work", "event_sequence"):
        for item in causal.get(field) or []:
            parts.append(item.get("description") if isinstance(item, dict) else item)
    return " ".join(str(item or "") for item in parts).lower()


def _infer_theme(
    benchmark: str,
    source_id: str,
    causal: dict[str, Any],
    native: dict[str, Any],
    instruction: str,
) -> tuple[str, str, str, list[str]]:
    if source_id in TB_COMPOSITIONS:
        group = TB_COMPOSITIONS[source_id][0]
        if group == "data-recovery-composite-v2":
            return (
                "partial_then_complete_result", "result_eventful",
                "The WAL recovery output completes an initially partial multi-source dataset.",
                ["late_or_out_of_order_superseded_result"],
            )
        if group == "secure-release-composite-v2":
            return (
                "task_scope_or_dependency_change", "live_eventful",
                "A repaired source/history dependency changes what can safely be deployed and logged live.",
                ["duplicate_or_replayed_completion", "delayed_authoritative_result"],
            )
        return (
            "straggler_under_resource_pressure", "resource_eventful",
            "Batch workers compete for a bounded inference budget on the critical path.",
            ["child_failure_or_implicit_error"],
        )
    text = _causal_text(causal)
    task_text = f"{instruction} {text}".lower()
    source_task_text = instruction.lower()
    event = causal.get("independent_event") or {}
    if benchmark == "MultiAgentBench":
        official_task = (native.get("_official_task") or {}).get("task") or {}
        roles = list((native.get("native_runtime") or {}).get("roles") or [])
        labels = list(official_task.get("labels") or [])
        source_scenario = str((native.get("source_binding") or {}).get("scenario") or "")
        if source_scenario == "database":
            theme = "conflicting_valid_results"
            rationale = (
                f"The database source requires reconciliation of {len(roles)} specialist probes across "
                f"{len(labels)} candidate root causes; competing valid observations require arbitration."
            )
        elif source_scenario == "bargaining":
            theme = "late_or_out_of_order_superseded_result"
            rationale = "Negotiation offers form a revision sequence; an older offer arriving late must not replace a newer accepted state."
        elif source_scenario == "coding":
            if re.search(r"idempot|repeat|duplicate|cache|memoiz|retry", source_task_text):
                theme = "duplicate_or_replayed_completion"
                rationale = "The coding source is explicitly repeat/retry/cache sensitive, so replay has an observable state consequence."
            elif re.search(r"test|pytest|debug|error|failure|exception|fault", source_task_text):
                theme = "child_failure_or_implicit_error"
                rationale = "The coding source has an explicit test/debug failure boundary, allowing a failed child module result to trigger recovery."
            elif re.search(r"concurr|parallel|thread|async", source_task_text):
                theme = "straggler_under_resource_pressure"
                rationale = "The coding source exposes concurrent workers or threads, allowing a real bounded-resource critical-path straggler."
            elif re.search(r"\bapi\b|network|http|web service", source_task_text):
                theme = "delayed_authoritative_result"
                rationale = "The coding source depends on an external API/network result that can become authoritative after provisional integration."
            elif re.search(r"security|authentication|permission|database|storage|persist", source_task_text):
                theme = "child_failure_or_implicit_error"
                rationale = "The coding source has a persistent security/storage boundary where an implicit child failure is observable and requires recovery."
            else:
                theme = "partial_then_complete_result"
                rationale = "The collaborative coding deliverable decomposes into modules whose early partial output must be retained then completed."
        elif source_scenario == "research":
            theme = "delayed_authoritative_result"
            rationale = "An independent research workstream can return authoritative cited evidence after a provisional synthesis persists."
        else:
            theme = "conflicting_valid_results"
            rationale = "Bound specialist workstreams can produce independently valid conclusions that require task-grounded arbitration."
    elif benchmark == "SWE-bench":
        evaluator = native.get("native_evaluator") or {}
        fail_tests = list(evaluator.get("FAIL_TO_PASS") or [])
        pass_tests = list(evaluator.get("PASS_TO_PASS") or [])
        test_files = {str(item).split("::", 1)[0] for item in [*fail_tests, *pass_tests]}
        if re.search(r"idempot|repeat|duplicate|cache|memoiz|retry", task_text):
            theme = "duplicate_or_replayed_completion"
            rationale = "The source behavior is repeat/retry/cache sensitive, so duplicate completion has an observable semantic effect."
        elif len(pass_tests) >= 40:
            theme = "straggler_under_resource_pressure"
            rationale = f"The bound regression closure has {len(pass_tests)} passing tests, supporting a real slow-suite critical path."
        elif len(fail_tests) > 1 or len(test_files) > 2:
            theme = "partial_then_complete_result"
            rationale = f"The source oracle spans {len(fail_tests)} repair tests and {len(test_files)} test files, allowing partial then complete evidence."
        elif re.search(r"dependenc|version|compatib|deprecat|configuration|option|plugin|backend", task_text):
            theme = "task_scope_or_dependency_change"
            rationale = "The repair is explicitly dependency/configuration sensitive, so a late dependency delta changes the affected closure."
        elif re.search(r"crash|exception|error|failure|fails to|cannot", task_text):
            theme = "child_failure_or_implicit_error"
            rationale = "The native reproduction is failure-bearing, enabling a real child-worker implicit-error/recovery event."
        else:
            theme = "late_or_out_of_order_superseded_result"
            rationale = "A clean-clone reproduction can arrive after an initial patch and authoritatively supersede its affected assumptions."
    elif benchmark == "OSWorld":
        domain = str((native.get("source_binding") or {}).get("domain") or "")
        evaluator = native.get("native_evaluator") or {}
        side_effectful = re.search(
            r"\b(send|email|create|add|append|insert|delete|remove|upload|post|save|account|calendar)\b",
            task_text,
        )
        duplicate_side_effectful = re.search(
            r"\b(send|email|upload|post|calendar|appointment|message|share|notify)\b",
            source_task_text,
        )
        if domain == "multi_apps" and duplicate_side_effectful:
            theme = "duplicate_or_replayed_completion"
            rationale = "The cross-application task performs a non-idempotent external side effect whose replay is directly observable."
        elif domain == "multi_apps":
            theme = "task_scope_or_dependency_change"
            rationale = "The source crosses application boundaries, so a late artifact dependency changes downstream work without invalidating all prior work."
        elif evaluator.get("func") == "infeasible" or domain == "chrome":
            theme = "delayed_authoritative_result"
            rationale = "A pinned browser/state observer supplies delayed authoritative truth after provisional desktop work persists."
        elif side_effectful:
            theme = "duplicate_or_replayed_completion"
            rationale = "The desktop task performs a persistent side effect; replay can be detected as an unwanted duplicate state transition."
        elif evaluator.get("result"):
            theme = "partial_then_complete_result"
            rationale = "The desktop artifact can be snapshotted before and after completion, yielding a real partial-to-complete transition."
        else:
            theme = "late_or_out_of_order_superseded_result"
            rationale = "A background desktop observer can arrive after persisted GUI work and supersede only the affected state."
    else:
        if re.search(r"duplicate|replay|already consumed|idempot", text):
            theme = "duplicate_or_replayed_completion"
            rationale = "The reviewed task mechanics explicitly contain replay, duplicate-consumption or idempotency risk."
        elif re.search(r"child fail|worker fail|failed result|implicit error|redelegat|timeout error", text):
            theme = "child_failure_or_implicit_error"
            rationale = "The reviewed task mechanics explicitly contain a failed/implicit-error child result requiring recovery."
        elif re.search(r"straggler|resource pressure|deadline|critical path|slow worker|budget", text):
            theme = "straggler_under_resource_pressure"
            rationale = "The reviewed task mechanics explicitly expose a slow worker, deadline or bounded-resource critical path."
        elif re.search(r"new requirement|scope change|dependency change|revised constraint|live dependency", text):
            theme = "task_scope_or_dependency_change"
            rationale = "The reviewed task mechanics explicitly change a requirement or dependency after useful work persists."
        elif re.search(r"partial|incomplete|remaining evidence|complete result", text):
            theme = "partial_then_complete_result"
            rationale = "The reviewed task mechanics explicitly distinguish partial evidence from a later complete result."
        elif re.search(r"conflict|two valid|disagree|arbitrat", text):
            theme = "conflicting_valid_results"
            rationale = "The reviewed task mechanics explicitly require arbitration between independently valid results."
        elif causal.get("superseded_work") or event.get("invalidates_event_id"):
            theme = "late_or_out_of_order_superseded_result"
            rationale = "The reviewed causal record identifies persisted work superseded by an independently produced result."
        else:
            theme = "delayed_authoritative_result"
            rationale = "An independently produced authoritative result becomes available after useful work has persisted."
    source_scenario = str((native.get("source_binding") or {}).get("scenario") or "")
    scenario = (
        "live_eventful"
        if benchmark == "OSWorld" or (benchmark == "MultiAgentBench" and source_scenario == "database")
        else "result_eventful"
    )
    if theme == "straggler_under_resource_pressure" or (
        benchmark == "MultiAgentBench"
        and source_scenario == "coding"
        and re.search(r"performance|scalab|high-volume|large-scale", source_task_text)
    ):
        scenario = "resource_eventful"
    alternatives = [
        item for item in THEME_CAPABILITIES
        if item != theme and item in {
            "delayed_authoritative_result",
            "late_or_out_of_order_superseded_result",
            "partial_then_complete_result",
            "child_failure_or_implicit_error",
            "duplicate_or_replayed_completion",
            "task_scope_or_dependency_change",
        }
    ][:2]
    return theme, scenario, rationale, alternatives


def _native_truth(native: dict[str, Any], benchmark: str) -> tuple[bool, list[str], list[str]]:
    evaluator = native.get("native_evaluator") or {}
    anchors: list[str] = []
    gaps: list[str] = []
    if benchmark == "SWE-bench":
        f2p = list(evaluator.get("FAIL_TO_PASS") or [])
        p2p = list(evaluator.get("PASS_TO_PASS") or [])
        anchors.extend([f"FAIL_TO_PASS:{item}" for item in f2p])
        anchors.extend([f"PASS_TO_PASS:{item}" for item in p2p[:8]])
        if not f2p:
            gaps.append("missing FAIL_TO_PASS native oracle tests")
    elif benchmark == "OSWorld":
        func = evaluator.get("func")
        expected = evaluator.get("expected")
        result = evaluator.get("result")
        if func:
            anchors.append(f"evaluator:{func}")
        if expected:
            anchors.append(f"expected:{_digest(expected)[:16]}")
        if result:
            anchors.append(f"result:{_digest(result)[:16]}")
        if func == "infeasible":
            anchors.append("private_oracle_reconstruction:required")
        elif not (func and result):
            gaps.append("OSWorld task lacks both a callable evaluator and observable result binding")
    elif benchmark == "MultiAgentBench":
        official = native.get("native_runtime") or {}
        task = (native.get("_official_task") or {}).get("task") or {}
        roles = list(official.get("roles") or [])
        environment = official.get("environment") or {}
        anchors.extend([f"role:{item.get('agent_id')}:{_digest(item.get('profile'))[:10]}" for item in roles])
        if environment:
            anchors.append(f"environment:{_digest(environment)[:16]}")
        if task.get("root_causes"):
            anchors.append(f"private_root_causes:{_digest(task.get('root_causes'))[:16]}")
        if task.get("labels"):
            anchors.append(f"answer_contract:{_digest(task.get('labels'))[:16]}:{task.get('number_of_labels_pred')}")
        if task.get("content") and task.get("output_format"):
            anchors.append(f"task_output_contract:{_digest({'content': task.get('content'), 'output_format': task.get('output_format')})[:16]}")
        if not roles:
            gaps.append("MultiAgentBench task lacks bound investigative roles")
        if not environment:
            gaps.append("MultiAgentBench task lacks authoritative environment configuration")
        if not task.get("content") or not task.get("output_format"):
            gaps.append("MultiAgentBench task lacks a complete source task/output contract")
    return not gaps, anchors, gaps


def _semantic_points(
    case_id: str,
    benchmark: str,
    native: dict[str, Any],
    production_case: dict[str, Any],
    instruction_sha: str,
) -> list[dict[str, Any]]:
    prefix = _slug(case_id, 24)
    points: list[dict[str, Any]] = []

    def add(description: str, anchor: str, method: str, critical: bool = False) -> None:
        if not description.strip() or any(item["description"] == description for item in points):
            return
        points.append({
            "id": f"{prefix}.sem.{len(points) + 1:02d}.{_slug(description, 28)}",
            "description": description.strip(),
            "source_anchor": anchor,
            "check_method": method,
            "critical": critical,
        })

    evaluator = native.get("native_evaluator") or {}
    if benchmark == "SWE-bench":
        for test in list(evaluator.get("FAIL_TO_PASS") or [])[:6]:
            add(f"The repaired repository passes source regression {test}.", f"FAIL_TO_PASS:{test}", "native_pytest", True)
        files: dict[str, list[str]] = {}
        for test in evaluator.get("PASS_TO_PASS") or []:
            files.setdefault(str(test).split("::", 1)[0], []).append(str(test))
        for path, tests in sorted(files.items())[:4]:
            add(
                f"Previously passing behavior in {path} remains intact ({len(tests)} bound tests).",
                f"PASS_TO_PASS_GROUP:{path}:{_digest(tests)[:12]}",
                "native_regression_group",
            )
        add(
            "The final patch is based on the pinned upstream commit and contains no evaluator-owned gold material.",
            f"base_commit:{(native.get('source_binding') or {}).get('base_commit')}",
            "git_and_leakage_audit",
            True,
        )
    elif benchmark == "OSWorld":
        if evaluator.get("func") == "infeasible":
            affected = [
                str(item.get("description") or "")
                for item in (production_case.get("causal_record") or {}).get("affected_work") or []
                if isinstance(item, dict)
            ]
            add(
                f"The final desktop state satisfies the task-specific observable state: {(affected[-1] if affected else 'the requested persisted state')[:220]}.",
                f"authored_private_oracle:{instruction_sha[:16]}",
                "task_specific_desktop_state_observer",
                True,
            )
            add(
                "The private observer confirms required state changes while forbidden account, profile, or application state remains unchanged.",
                f"preservation_snapshot:{instruction_sha[16:32]}",
                "before_after_state_diff",
                True,
            )
        else:
            add(
                f"The persisted desktop artifact passes the bound OSWorld evaluator {evaluator.get('func')}.",
                f"evaluator:{evaluator.get('func')}:{_digest(evaluator.get('expected'))[:12]}",
                "native_osworld_evaluator",
                True,
            )
            add(
                f"The required result artifact remains at {_text(evaluator.get('result'))[:220]}.",
                f"result_spec:{_digest(evaluator.get('result'))[:16]}",
                "artifact_observer",
                True,
            )
    elif benchmark == "MultiAgentBench":
        official = native.get("_official_task") or {}
        task = official.get("task") or {}
        scenario = str(official.get("scenario") or (native.get("source_binding") or {}).get("scenario") or "")
        roots = list(task.get("root_causes") or [])
        labels = list(task.get("labels") or [])
        predicted_count = task.get("number_of_labels_pred")
        if roots:
            add(
                f"The final diagnosis contains the authoritative root-cause set of cardinality {len(roots)}.",
                f"private_root_causes:{_digest(roots)[:16]}",
                "native_label_evaluator",
                True,
            )
        if predicted_count:
            add(
                f"The final answer selects exactly {predicted_count} labels as required by the native output contract.",
                f"native_output_cardinality:{predicted_count}:{_digest(labels)[:12]}",
                "native_output_contract",
                True,
            )
        add(
            "The final deliverable obeys the native output-format contract without exposing evaluator-owned truth.",
            f"native_output_format:{_digest(task.get('output_format'))[:16]}",
            "native_output_schema_probe",
            True,
        )
        if scenario == "coding":
            add(
                "The requested program passes task-specific hidden functional tests derived from the source requirements.",
                f"authored_coding_oracle:{instruction_sha[:16]}",
                "task_specific_functional_test_suite",
                True,
            )
        elif scenario == "bargaining":
            add(
                "The final negotiation ledger records a mutually consistent agreement and obeys all source price/term constraints.",
                f"authored_bargaining_oracle:{instruction_sha[:16]}",
                "deterministic_negotiation_ledger_probe",
                True,
            )
        elif scenario == "research":
            add(
                "The final synthesis is supported by the pinned evidence corpus and every material citation resolves to its claimed evidence.",
                f"authored_research_oracle:{instruction_sha[:16]}",
                "pinned_corpus_claim_citation_probe",
                True,
            )
        for role in list((native.get("native_runtime") or {}).get("roles") or []):
            agent_id = str(role.get("agent_id") or "specialist")
            profile = str(role.get("profile") or "")
            add(
                f"Evidence produced by bound role {agent_id} is consumed or explicitly ruled out according to its task: {profile[:180]}.",
                f"role:{agent_id}:{_digest(profile)[:16]}",
                "native_role_evidence_probe",
            )
        for label in labels:
            add(
                f"Candidate conclusion {label} is explicitly supported or eliminated by native environment evidence.",
                f"candidate_label:{label}:{_digest(task.get('content'))[:12]}",
                "native_candidate_disposition_probe",
            )
        add(
            "The final diagnosis is supported by observations from the bound specialist roles, not an unverified guess.",
            f"roles:{_digest((native.get('native_runtime') or {}).get('roles') or [])[:16]}",
            "native_transcript_and_environment_probe",
            True,
        )

    for point in production_case.get("score_points") or []:
        add(
            str(point.get("description") or ""),
            f"reviewed_causal_record:{point.get('id')}:{instruction_sha[:12]}",
            "task_specific_hidden_assertion",
            str(point.get("id")) in {"closure_verified", "required_action_01"},
        )
    add(
        "All source requirements represented by the instruction digest remain satisfied in the final state.",
        f"instruction_sha256:{instruction_sha}",
        "requirements_manifest_and_hidden_verifier",
        True,
    )

    causal = production_case.get("causal_record") or {}
    causal_fields = (
        ("prior_work", "preservation", "The final state preserves valid prior work"),
        ("affected_work", "affected_closure", "The final state correctly realizes affected work"),
        ("superseded_work", "stale_exclusion", "The final state excludes superseded work"),
        ("event_sequence", "event_sequence", "The auditable execution reaches the task-specific milestone"),
    )
    for field, category, lead in causal_fields:
        for index, item in enumerate(causal.get(field) or [], 1):
            description = str(item.get("description") if isinstance(item, dict) else item or "").strip()
            if description:
                add(
                    f"{lead}: {description}",
                    f"causal:{category}:{index}:{_digest(description)[:14]}",
                    f"task_specific_{category}_probe",
                    field in {"affected_work", "superseded_work"} and index == 1,
                )
    independent = causal.get("independent_event") or {}
    event_description = str(independent.get("description") or "").strip()
    if event_description:
        add(
            f"The final artifact records and semantically consumes the independent event: {event_description}",
            f"independent_event:{_digest(independent)[:16]}",
            "event_receipt_and_outcome_probe",
            True,
        )

    return points


def _build_case_ir(
    case_id: str,
    theme: str,
    causal: dict[str, Any],
    semantic: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    prior = [str(item.get("description") or "") for item in causal.get("prior_work") or [] if isinstance(item, dict)]
    affected = [str(item.get("description") or "") for item in causal.get("affected_work") or [] if isinstance(item, dict)]
    event_description = str((causal.get("independent_event") or {}).get("description") or causal.get("async_stressor") or "authoritative independent result")
    if not prior:
        prior = ["The source baseline and already verified independent artifacts remain valid."]
    if not affected:
        affected = [point["description"] for point in semantic[:3]] or ["Reconcile the final source task outcome."]
    affected = affected[:4]
    requirements = []
    for index, description in enumerate(affected, 1):
        requirements.append({
            "id": f"req.{index:02d}.{_slug(description, 24)}",
            "description": description,
            "public_evidence": f"source instruction and workstream result for {_slug(description, 36)}",
            "observable_probe": semantic[min(index - 1, len(semantic) - 1)]["id"],
        })
    nodes = [{"id": "event_input", "kind": "event"}]
    nodes += [{"id": requirement["id"], "kind": "requirement"} for requirement in requirements]
    nodes += [{"id": "final_state", "kind": "closure"}, {"id": "preserve_prior", "kind": "preservation"}]
    edges = [{"source": "event_input", "target": requirement["id"], "relation": "invalidates"} for requirement in requirements]
    edges += [{"source": requirement["id"], "target": "final_state", "relation": "depends_on"} for requirement in requirements]
    affected_closure = ["event_input", *[item["id"] for item in requirements], "final_state"]
    baseline_anchor = semantic[-1]["id"]
    outcome_anchors = [item["id"] for item in semantic[:max(1, min(4, len(semantic)))]]
    decisions = []
    target = requirements[0]
    for index, (obligation, stage, mutation, gate) in enumerate(THEME_DECISIONS[theme], 1):
        prior_excerpt = prior[(index - 1) % len(prior)]
        affected_excerpt = affected[(index - 1) % len(affected)]
        required = (
            f"For event '{event_description}', perform {obligation} for '{affected_excerpt}' "
            f"while retaining valid prior result '{prior_excerpt}'."
        )
        forbidden = (
            f"Do not handle {obligation} by ignoring the event, retaining a displaced state, "
            f"or invalidating the preserved prior result '{prior_excerpt}'."
        )
        decisions.append({
            "id": f"{index:02d}_{_slug(obligation, 28)}_{_slug(affected_excerpt, 18)}",
            "decision_group": f"{_slug(obligation, 28)}_{_slug(affected_excerpt, 28)}",
            "obligation": obligation,
            "stage_tag": stage,
            "task_requirement_id": target["id"],
            "required_behavior": required,
            "forbidden_behavior": forbidden,
            "primary_evidence": f"gateway event receipt joined to {', '.join(outcome_anchors)}",
            "outcome_anchors": outcome_anchors,
            "mutation_family": mutation,
            "gate": gate,
            "gate_args": {
                "artifacts": ["final_state"],
                "preserve_artifacts": ["preserve_prior"],
                "workstreams": [target["id"]],
            },
            "must_still_pass": [baseline_anchor],
            "critical": index == 1 or stage == "closure",
        })
    ir = {
        "schema_version": "1",
        "case_id": case_id,
        "instance_id": "seed-1",
        "task_archetype": "source_native_task_causal_rebuild",
        "task_requirements": requirements,
        "dependency_graph": {"nodes": nodes, "edges": edges},
        "event_contract": {
            "event_id": f"evt.{_slug(case_id, 24)}.{_slug(theme, 24)}",
            "primary_event_theme": theme,
            "before_state": str(causal.get("async_stressor") or "useful source work is already persisted"),
            "after_state": event_description,
            "affected_nodes": ["event_input"],
            "affected_closure": affected_closure,
            "unaffected_nodes": ["preserve_prior"],
        },
        "decision_contracts": decisions,
    }
    ir_errors = validate_case_ir(ir)
    if ir_errors:
        raise ValueError(f"generated invalid Case IR for {case_id}: {ir_errors}")
    plan = compile_score_plan(ir, _slug(case_id, 18))
    plan_errors = validate_score_plan(plan)
    if plan_errors:
        raise ValueError(f"generated invalid score plan for {case_id}: {plan_errors}")
    return ir, plan


def _runtime_plan(benchmark: str, native: dict[str, Any], source_id: str) -> dict[str, Any]:
    runtime = native.get("native_runtime") or {}
    if benchmark == "SWE-bench":
        evaluator = native.get("native_evaluator") or {}
        return {
            "environment_strategy": "rebuild official SWE-bench instance image from repo/base_commit when image is absent",
            "docker": ["pinned base image", "repository checkout", "test dependencies", "non-root participant workspace"],
            "assets": ["problem statement", "base commit", "FAIL_TO_PASS", "PASS_TO_PASS", "selected reproduction command"],
            "event_injection": "run reproduction/regression worker in a clean clone and release bounded output after a persisted main diff",
            "oracle": "apply an evaluator-owned correct patch, then execute FAIL_TO_PASS and PASS_TO_PASS",
            "hidden_tests": "unchanged native SWE tests plus patch-scope, lineage, stale-patch and post-event regression assertions",
            "missing_environment_is_reconstructable": True,
            "native_runtime_ref": runtime,
            "native_test_count": len(evaluator.get("FAIL_TO_PASS") or []) + len(evaluator.get("PASS_TO_PASS") or []),
        }
    if benchmark == "OSWorld":
        evaluator = native.get("native_evaluator") or {}
        domain = str((native.get("source_binding") or {}).get("domain") or "desktop")
        custom_oracle = evaluator.get("func") == "infeasible"
        custom_strategies = {
            "thunderbird": "inspect prefs.js/account identities and query a local mock SMTP endpoint; assert outgoing-only configuration and absence of an incoming service",
            "chrome": "inspect pinned Chrome Local State/Preferences and launch-state behavior; assert the requested flag state survives restart",
            "os": "observe the active desktop session/user and hash account databases before/after; assert the requested user switch without logout or account mutation",
        }
        oracle_strategy = custom_strategies.get(
            domain,
            "author a deterministic observer over the task-specific application state and a before/after preservation snapshot",
        )
        return {
            "environment_strategy": "build a pinned desktop/LibreOffice VM or container and mirror all cloud assets into an evaluator-owned cache",
            "docker": ["desktop base snapshot", "LibreOffice/apps", "pyautogui bridge", "artifact observer sidecar"],
            "assets": ["official setup config", "expected artifact", "input artifacts", "result path", "font/locale lock"],
            "event_injection": "read-only worker extracts or validates a source artifact on a snapshot clone; release after a persisted GUI checkpoint",
            "oracle": (
                oracle_strategy if custom_oracle
                else f"replay an evaluator-owned artifact construction and score with {evaluator.get('func')}"
            ),
            "hidden_tests": (
                "task-specific state observer, forbidden-state diff, event receipt, preservation and restart/closure assertions"
                if custom_oracle else
                "native OSWorld evaluator plus OOXML/ODF structure, target path, formatting, preservation and post-event save checks"
            ),
            "requires_authored_private_oracle": custom_oracle,
            "oracle_reconstruction_domain": domain if custom_oracle else None,
            "missing_environment_is_reconstructable": True,
            "native_runtime_ref": runtime,
        }
    if benchmark == "MultiAgentBench":
        scenario = str((native.get("source_binding") or {}).get("scenario") or "")
        custom_oracle = scenario != "database"
        custom_strategies = {
            "coding": "derive a private functional/property test suite from each program requirement and execute it in a clean participant clone",
            "bargaining": "score a deterministic negotiation ledger for agreement consistency, price/term constraints, chronology and prohibited concessions",
            "research": "pin an evaluator-owned evidence corpus and verify claim/citation entailment, source coverage and unsupported-claim exclusion",
        }
        return {
            "environment_strategy": "stage the pinned MARBLE task with a containerized database/game runtime and harness-owned transcript journal",
            "docker": ["MARBLE engine", "scenario-specific service", "tool gateway", "state-attestation sidecar"],
            "assets": ["official task config", "environment seed", "role profiles", "private root-cause truth", "query/action journal"],
            "event_injection": "execute a real bound specialist role and release its raw result only after a persisted environment action",
            "oracle": (
                custom_strategies.get(scenario)
                if custom_oracle else
                "run all bound roles/tools, reconcile against private root-cause truth and emit the exact source answer contract"
            ),
            "hidden_tests": "native accuracy plus evidence coverage, exact label cardinality, eliminated alternatives, authority consumption and closure",
            "requires_authored_private_oracle": custom_oracle,
            "oracle_reconstruction_domain": scenario if custom_oracle else None,
            "missing_environment_is_reconstructable": True,
            "native_runtime_ref": runtime,
        }
    return {
        "environment_strategy": "copy the locked Terminal-Bench task image/assets and extend it with evaluator-owned event staging",
        "docker": ["locked upstream Dockerfile", "pinned dependencies", "participant service", "private verifier clone"],
        "assets": ["upstream task assets", "event assets", "authority receipts", "canonical/equivalent solutions"],
        "event_injection": f"task-specific event plan for {source_id} bound to persisted filesystem/service state",
        "oracle": "compose the upstream canonical solutions and rederive final state after the injected event",
        "hidden_tests": "upstream semantics plus task-specific preservation, stale exclusion, runtime behavior, lineage and closure assertions",
        "missing_environment_is_reconstructable": True,
        "native_runtime_ref": runtime,
    }


def _composition(source_id: str, benchmark: str, case_id: str, causal: dict[str, Any]) -> dict[str, Any]:
    if source_id in TB_COMPOSITIONS:
        proposed, upstream, rationale = TB_COMPOSITIONS[source_id]
    else:
        proposed, upstream = f"formal-{case_id}", [source_id]
        rationale = (
            "The upstream task is already deep enough to preserve source fidelity; depth comes from independent "
            "evidence production, affected-state revision, preservation and closure rather than unrelated task concatenation."
        )
    prior = [str(item.get("description") or "") for item in causal.get("prior_work") or [] if isinstance(item, dict)]
    affected = [str(item.get("description") or "") for item in causal.get("affected_work") or [] if isinstance(item, dict)]
    event = str((causal.get("independent_event") or {}).get("description") or causal.get("async_stressor") or "independent authority")
    milestones = [
        {"id": "establish_source_baseline", "depends_on": [], "description": prior[0] if prior else "Establish the pinned source baseline."},
        {"id": "produce_independent_evidence", "depends_on": [], "description": event},
        {"id": "persist_initial_affected_work", "depends_on": ["establish_source_baseline"], "description": affected[0] if affected else "Persist useful initial work."},
        {"id": "revise_affected_closure", "depends_on": ["produce_independent_evidence", "persist_initial_affected_work"], "description": affected[1] if len(affected) > 1 else "Revise the exact affected closure."},
        {"id": "verify_final_closure", "depends_on": ["revise_affected_closure"], "description": affected[-1] if affected else "Reverify the final source outcome."},
    ]
    return {
        "proposed_case_id": proposed,
        "upstream_task_count": len(upstream),
        "upstream_task_ids": upstream,
        "rationale": rationale,
        "milestones": milestones,
        "dependency_edges": [
            {"source": dependency, "target": item["id"]}
            for item in milestones for dependency in item["depends_on"]
        ],
    }


def _experiment_standard_audit(
    benchmark: str,
    composition: dict[str, Any],
    semantic: list[dict[str, Any]],
    control: list[dict[str, Any]],
    transformable: bool,
) -> dict[str, Any]:
    blueprint_checks = {
        "authoritative_source_truth": transformable,
        "upstream_task_count_1_to_4": 1 <= int(composition["upstream_task_count"]) <= 4,
        "end_to_end_dependency_graph": bool(composition.get("dependency_edges")),
        "semantic_points_are_source_anchored": bool(semantic),
        "control_points_are_causally_required": bool(control),
        "case_specific_semantic_anchors": len({item["source_anchor"] for item in semantic}) == len(semantic),
        "case_specific_control_contracts": len({item["id"] for item in control}) == len(control),
    }
    implementation_gates = [
        "materialize Docker/VM image, pinned assets and participant task bundle",
        "implement a real evaluator-owned asynchronous event and observable release receipt",
        "implement every independently justified semantic and causal control check, without count padding",
        "implement canonical plus at least one equivalent solution",
        "execute at least two targeted negative mutations before acceptance, then at least 40 for calibration",
        "pass Oracle, hidden verifier, public/private boundary, leakage and provenance validation",
        "obtain genuine human case review; prior model-generated reviews do not satisfy this gate",
        "run multi-model calibration and reject correlated or degenerate score points",
        "freeze immutable bundle/verifier digests and register the family-instance pair",
    ]
    return {
        "technically_transformable": transformable,
        "blueprint_has_independent_evidence_contracts": all(blueprint_checks.values()),
        "blueprint_checks": blueprint_checks,
        "formal_registry_ready_now": False,
        "artifact_stage": "per-case audited transformation blueprint; executable formal package not yet materialized",
        "implementation_gates_before_registry": implementation_gates,
    }


def build_transformability_audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    v4_root = root / "artifacts/source-native-v4"
    legacy_root = root / "artifacts/unified-case-set-v3/03-unified-production"
    production_root = root / "artifacts/authoritative-expansion-v2/03-case-production"
    production_manifest = {
        str(item.get("source_task_id")): item
        for item in _jsonl(production_root / "case_manifest.jsonl")
    }
    raw: list[tuple[str, dict[str, Any]]] = [
        ("source-native-v4", item) for item in _jsonl(v4_root / "native_manifest.jsonl")
    ]
    raw += [
        ("unified-v3", item)
        for item in _jsonl(legacy_root / "case_manifest.jsonl")
        if str(item.get("benchmark")) == "Terminal-Bench"
    ]
    rows: list[dict[str, Any]] = []
    for collection, manifest in raw:
        case_id = str(manifest["case_id"])
        benchmark = str(manifest["benchmark"])
        source_id = str(manifest["source_task_id"])
        if collection == "source-native-v4":
            native_dir = v4_root / str(manifest["native_path"])
            native = _json(native_dir / "native_case.json")
            official_task_path = native_dir / "official_task.json"
            if official_task_path.is_file():
                native["_official_task"] = _json(official_task_path)
            production_manifest_row = production_manifest.get(source_id)
            production_dir = (
                production_root / str(production_manifest_row["path"])
                if production_manifest_row else None
            )
            production_case = _json(production_dir / "case.json") if production_dir and (production_dir / "case.json").is_file() else {}
            instruction = _source_instruction(native_dir, benchmark, production_case)
            native_ok, native_anchors, native_gaps = _native_truth(native, benchmark)
            native_source_paths = [
                path for path in (
                    native_dir / "native_case.json",
                    native_dir / "participant_task.json",
                    native_dir / "official_task.json",
                    native_dir / "native_config.yaml",
                    native_dir / "task_meta.json",
                    native_dir / "evaluation_binding.json",
                ) if path.is_file()
            ]
            source_files = [str(path.relative_to(root)).replace("\\", "/") for path in native_source_paths]
            causal = production_case.get("causal_record") or {}
        else:
            production_dir = legacy_root / str(manifest["path"])
            production_case = _json(production_dir / "case.json")
            source_record = _json(production_dir / "source_record.json")
            instruction = str((production_case.get("source") or {}).get("instruction") or source_record.get("instruction") or "")
            native = {"native_runtime": {"adapter": "terminal-bench locked task bundle"}, "native_evaluator": {"score_points": production_case.get("score_points") or []}}
            native_ok = bool(production_case.get("score_points"))
            native_anchors = [f"legacy_score_point:{item.get('id')}" for item in production_case.get("score_points") or []]
            native_gaps = [] if native_ok else ["missing Terminal-Bench oracle score anchors"]
            source_files = [
                str(path.relative_to(root)).replace("\\", "/")
                for path in (production_dir / "case.json", production_dir / "task.md", production_dir / "source_record.json")
                if path.is_file()
            ]
            native_source_paths = [root / path for path in source_files]
            causal = production_case.get("causal_record") or {}
        instruction_sha = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
        source_gaps = []
        if len(instruction.strip()) < 20:
            source_gaps.append("source instruction is absent or too short")
        if not causal.get("independent_event"):
            source_gaps.append("reviewed causal record lacks an independent event")
        if not causal.get("affected_work"):
            source_gaps.append("reviewed causal record lacks affected work")
        hard_blockers = [*source_gaps, *native_gaps]
        transformable = not hard_blockers
        theme, scenario, classification_rationale, alternative_themes = _infer_theme(
            benchmark, source_id, causal, native, instruction,
        )
        semantic = _semantic_points(case_id, benchmark, native, production_case, instruction_sha)
        if len(semantic) < 4:
            hard_blockers.append("fewer than four source-anchored semantic score points can be authored")
            transformable = False
        case_ir = score_plan = None
        if transformable:
            case_ir, score_plan = _build_case_ir(case_id, theme, causal, semantic)
        composition = _composition(source_id, benchmark, case_id, causal)
        runtime = _runtime_plan(benchmark, native, source_id)
        control_points = (score_plan or {}).get("points") or []
        requires_custom_oracle = bool(runtime.get("requires_authored_private_oracle"))
        if not transformable:
            disposition = "not_transformable_without_new_source_truth"
        elif requires_custom_oracle and benchmark == "OSWorld":
            disposition = "transformable_author_custom_oracle_and_desktop_runtime"
        elif requires_custom_oracle and benchmark == "MultiAgentBench":
            disposition = "transformable_author_custom_oracle_and_native_service_runtime"
        elif bool(manifest.get("runtime_ready")) or benchmark == "Terminal-Bench":
            disposition = "transformable_runtime_near_ready"
        elif benchmark == "OSWorld":
            disposition = "transformable_rebuild_desktop_runtime_and_assets"
        elif benchmark == "MultiAgentBench":
            disposition = "transformable_rebuild_native_service_runtime"
        else:
            disposition = "transformable_rebuild_official_test_runtime"
        row = {
            "case_id": case_id,
            "source_collection": collection,
            "benchmark": benchmark,
            "source_task_id": source_id,
            "legacy_generation_family": manifest.get("family"),
            "transformability": {
                "can_be_formal_case_task": transformable,
                "disposition": disposition,
                "hard_blockers": hard_blockers,
                "runtime_absence_is_not_a_rejection": True,
                "native_truth_available": native_ok,
            },
            "source_audit": {
                "instruction_sha256": instruction_sha,
                "instruction_chars": len(instruction),
                "source_files": source_files,
                "source_file_sha256": {
                    str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in native_source_paths
                },
                "native_oracle_anchors": native_anchors,
                "production_case_path": (
                    str(production_dir.relative_to(root)).replace("\\", "/") if production_dir else None
                ),
            },
            "composition_plan": composition,
            "async_classification_plan": {
                "primary_event_theme": theme,
                "async_scenario_class": scenario,
                "capabilities": THEME_CAPABILITIES[theme],
                "classification_basis": "source-native task/runtime/evaluator mechanics with reviewed causal details; legacy generation family is not used as the formal label",
                "classification_rationale": classification_rationale,
                "alternative_event_themes": alternative_themes,
            },
            "runtime_package_plan": runtime,
            "semantic_score_blueprint": semantic,
            "case_ir_blueprint": case_ir,
            "control_score_blueprint": control_points,
            "negative_mutation_blueprint": (score_plan or {}).get("negative_mutations") or [],
            "experiment_standard_audit": _experiment_standard_audit(
                benchmark, composition, semantic, control_points, transformable,
            ),
        }
        row["semantic_design_digest"] = _digest(semantic)
        row["control_design_digest"] = _digest(row["control_score_blueprint"])
        rows.append(row)
    ids = [row["case_id"] for row in rows]
    if len(rows) != 607 or len(set(ids)) != 607:
        raise ValueError(f"expected 607 unique generated records, found {len(rows)} rows/{len(set(ids))} ids")
    transformable_rows = [row for row in rows if row["transformability"]["can_be_formal_case_task"]]
    proposed_rows_by_id: dict[str, dict[str, Any]] = {}
    for row in transformable_rows:
        proposed_rows_by_id.setdefault(row["composition_plan"]["proposed_case_id"], row)
    proposed_rows = list(proposed_rows_by_id.values())
    allocation_availability = Counter(
        (
            row["async_classification_plan"]["primary_event_theme"],
            row["async_classification_plan"]["async_scenario_class"],
        )
        for row in proposed_rows
    )
    allocation_gaps = []
    for theme, scenarios in BALANCED_450_ALLOCATION.items():
        for scenario, required in scenarios.items():
            available = allocation_availability[(theme, scenario)]
            if available < required:
                allocation_gaps.append({
                    "theme": theme, "scenario": scenario,
                    "required": required, "available": available,
                })
    summary = {
        "input_count": len(rows),
        "transformable_count": sum(row["transformability"]["can_be_formal_case_task"] for row in rows),
        "not_transformable_count": sum(not row["transformability"]["can_be_formal_case_task"] for row in rows),
        "benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in rows).items())),
        "disposition_counts": dict(sorted(Counter(row["transformability"]["disposition"] for row in rows).items())),
        "primary_event_theme_counts": dict(sorted(Counter(row["async_classification_plan"]["primary_event_theme"] for row in rows if row["transformability"]["can_be_formal_case_task"]).items())),
        "async_scenario_class_counts": dict(sorted(Counter(row["async_classification_plan"]["async_scenario_class"] for row in rows if row["transformability"]["can_be_formal_case_task"]).items())),
        "upstream_task_count_distribution": dict(sorted(Counter(str(row["composition_plan"]["upstream_task_count"]) for row in rows).items())),
        "unique_proposed_case_count": len({row["composition_plan"]["proposed_case_id"] for row in rows if row["transformability"]["can_be_formal_case_task"]}),
        "unique_proposed_upstream_task_count_distribution": dict(sorted(Counter(str(row["composition_plan"]["upstream_task_count"]) for row in proposed_rows).items())),
        "balanced_450_event_scenario_allocation_feasible": not allocation_gaps,
        "balanced_450_event_scenario_allocation": BALANCED_450_ALLOCATION,
        "balanced_450_allocation_gaps": allocation_gaps,
        "custom_private_oracle_required_count": sum(bool(row["runtime_package_plan"].get("requires_authored_private_oracle")) for row in transformable_rows),
        "independently_anchored_blueprint_count": sum(row["experiment_standard_audit"]["blueprint_has_independent_evidence_contracts"] for row in transformable_rows),
        "semantic_point_count_distribution": dict(sorted(Counter(str(len(row["semantic_score_blueprint"])) for row in transformable_rows).items(), key=lambda item: int(item[0]))),
        "control_point_count_distribution": dict(sorted(Counter(str(len(row["control_score_blueprint"])) for row in transformable_rows).items(), key=lambda item: int(item[0]))),
        "formal_registry_ready_now_count": sum(row["experiment_standard_audit"]["formal_registry_ready_now"] for row in transformable_rows),
        "duplicate_semantic_design_count": len(transformable_rows) - len({row["semantic_design_digest"] for row in transformable_rows}),
        "duplicate_control_design_count": len(transformable_rows) - len({row["control_design_digest"] for row in transformable_rows}),
    }
    return {"schema_version": "1.0", "summary": summary, "rows": rows}


def write_transformability_audit(audit: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rows = list(audit["rows"])
    (output / "summary.json").write_text(
        json.dumps(audit["summary"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output / "cases.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (output / "case-index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "case_id", "benchmark", "source_task_id", "can_transform", "disposition",
            "proposed_case_id", "upstream_task_count", "primary_event_theme",
            "async_scenario_class", "semantic_points", "control_points", "hard_blockers",
            "formal_registry_ready_now",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "case_id": row["case_id"],
                "benchmark": row["benchmark"],
                "source_task_id": row["source_task_id"],
                "can_transform": row["transformability"]["can_be_formal_case_task"],
                "disposition": row["transformability"]["disposition"],
                "proposed_case_id": row["composition_plan"]["proposed_case_id"],
                "upstream_task_count": row["composition_plan"]["upstream_task_count"],
                "primary_event_theme": row["async_classification_plan"]["primary_event_theme"],
                "async_scenario_class": row["async_classification_plan"]["async_scenario_class"],
                "semantic_points": len(row["semantic_score_blueprint"]),
                "control_points": len(row["control_score_blueprint"]),
                "hard_blockers": "; ".join(row["transformability"]["hard_blockers"]),
                "formal_registry_ready_now": row["experiment_standard_audit"]["formal_registry_ready_now"],
            })
