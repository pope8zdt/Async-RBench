"""Fail-closed audit for registered and generated Async-RBench case tasks.

The generated v3/v4 collections use ``family`` as a production label.  Those
labels are not Async-RBench event classifications and must never be copied into
the official registry.  This audit keeps the concepts separate and only calls a
task publication-ready when it has the complete task-causal runtime and scoring
contract required by the frozen experiment design.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

import yaml

from .case_quality import validate_case_quality
from .case_ir import validate_case_ir, validate_score_plan
from .retrospective_quality import build_retrospective_quality_audit
from .spec import discover_case_instances, discover_cases, load_case_registry, validate_case_registry


FORMAL_RUNTIME_FILES = (
    "public_case.yaml",
    "private/private_case.yaml",
    "task/task.yaml",
    "task/Dockerfile",
    "task/docker-compose.yaml",
    "task/run-tests.sh",
    "task/oracle.sh",
    "task/tests/semantic_checks.json",
    "task/tests/control_flow_checks.json",
    "task/tests/test_case_outcomes.py",
    "generate.py",
    "oracle.py",
    "verify.py",
    "PROVENANCE.md",
)

TASK_CAUSAL_FILES = (
    "private/case_ir.json",
    "private/score_plan.json",
)

EVENT_THEMES = {
    "delayed_authoritative_result",
    "late_or_out_of_order_superseded_result",
    "partial_then_complete_result",
    "conflicting_valid_results",
    "duplicate_or_replayed_completion",
    "child_failure_or_implicit_error",
    "task_scope_or_dependency_change",
    "straggler_under_resource_pressure",
}

SCENARIO_CLASSES = {"result_eventful", "live_eventful", "resource_eventful"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _checks(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    value = _read_json(path)
    return list(value.get("checks") or []) if isinstance(value, dict) else []


def _normalize_benchmark(value: str) -> str:
    aliases = {
        "swe-bench": "swe-bench",
        "terminal-bench": "terminal-bench",
        "gaia2": "gaia2",
        "gaia": "gaia",
        "multiagentbench": "multiagentbench",
        "osworld": "osworld",
    }
    return aliases.get(value.strip().lower(), value.strip().lower())


def _instance_dir(root: Path, reference: Any) -> Path:
    return Path(reference.case_dir)


def _registered_rows(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    references = discover_case_instances(root)
    registry, registry_errors = load_case_registry(root)
    technical_errors = list(registry_errors)
    technical_errors.extend(validate_case_registry(root, discover_cases(root)))
    split_map = {
        (str(family["case_id"]), str(instance["instance_id"])): str(instance["split"])
        for family in (registry or {}).get("case_families") or []
        for instance in family.get("instances") or []
    }
    retro = build_retrospective_quality_audit(root, references)
    retro_index = {
        (row["case_id"], row["instance_id"]): row for row in retro["rows"]
    }
    rows: list[dict[str, Any]] = []
    for reference in references:
        case_dir = _instance_dir(root, reference)
        public = yaml.safe_load((case_dir / "public_case.yaml").read_text(encoding="utf-8")) or {}
        private = yaml.safe_load(
            (case_dir / "private/private_case.yaml").read_text(encoding="utf-8")
        ) or {}
        semantic = _checks(case_dir / "task/tests/semantic_checks.json")
        control = _checks(case_dir / "task/tests/control_flow_checks.json")
        classification = private.get("classification") or {}
        primary = str(classification.get("primary_event_theme") or "")
        scenario = str(classification.get("async_scenario_class") or "")
        dimensions = {str(item.get("dimension") or "") for item in control}
        decision_groups = {str(item.get("decision_group") or "") for item in control}
        quality_errors = validate_case_quality(root, case_dir, require_contract=True)
        missing_runtime = [path for path in FORMAL_RUNTIME_FILES if not (case_dir / path).is_file()]
        missing_causal = [path for path in TASK_CAUSAL_FILES if not (case_dir / path).is_file()]
        row_retro = retro_index[(reference.case_id, reference.instance_id)]
        gates = {
            "registry_technical_contract": not technical_errors,
            "complete_runtime_package": not missing_runtime,
            "valid_async_classification": primary in EVENT_THEMES and scenario in SCENARIO_CLASSES,
            "task_specific_semantic_registry": bool(semantic),
            "task_specific_control_registry": bool(control) and not ("" in dimensions),
            "causal_decision_groups": bool(control) and "" not in decision_groups,
            "task_causal_case_ir": not missing_causal,
            "quality_contract": not quality_errors,
            "source_instruction_fidelity": all(
                source.get("task_instruction_available") and source.get("verbatim_preserved")
                for source in row_retro.get("source_tasks") or []
            ),
            "equivalence_solution_executed": row_retro.get("equivalence_solution_count", 0) >= 1,
            "negative_mutations_executed": row_retro.get("negative_mutation_count", 0) >= 2,
        }
        failed = [name for name, passed in gates.items() if not passed]
        rows.append({
            "case_task_id": f"{reference.case_id}/{reference.instance_id}",
            "case_id": reference.case_id,
            "instance_id": reference.instance_id,
            "benchmark": str(reference.benchmark),
            "split": split_map[(reference.case_id, reference.instance_id)],
            "primary_event_theme": primary or None,
            "secondary_event_themes": list(classification.get("secondary_event_themes") or []),
            "async_scenario_class": scenario or None,
            "capabilities": sorted(map(str, private.get("capabilities") or [])),
            "semantic_check_count": len(semantic),
            "control_flow_check_count": len(control),
            "control_dimensions": sorted(dimensions - {""}),
            "decision_groups": sorted(decision_groups - {""}),
            "missing_runtime_files": missing_runtime,
            "missing_task_causal_files": missing_causal,
            "quality_errors": quality_errors,
            "gates": gates,
            "failed_gates": failed,
            "publication_ready": not failed,
        })
    return rows, {
        "technical_registry_valid": not technical_errors,
        "technical_registry_errors": technical_errors,
        "publication_ready_count": sum(row["publication_ready"] for row in rows),
        "task_count": len(rows),
        "primary_event_theme_counts": dict(sorted(Counter(
            str(row["primary_event_theme"]) for row in rows
        ).items())),
        "async_scenario_class_counts": dict(sorted(Counter(
            str(row["async_scenario_class"]) for row in rows
        ).items())),
        "capability_counts": dict(sorted(Counter(
            capability for row in rows for capability in row["capabilities"]
        ).items())),
    }


def _pilot_evidence(root: Path) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "models": set(), "modes": set(), "counts": Counter(), "produced": 0,
    })
    episode_root = root / "artifacts/native-model-pilot-v1"
    if not episode_root.is_dir():
        return {}
    for path in episode_root.glob("run-*/episodes/*/*/*.json"):
        try:
            row = _read_json(path)
        except (OSError, ValueError, TypeError):
            continue
        case_id = str(row.get("case_id") or "")
        model = str(row.get("model") or "")
        mode = str(row.get("mode") or "")
        if not case_id or not model or mode not in {"linear", "async", "react"}:
            continue
        item = evidence[case_id]
        item["models"].add(model)
        item["modes"].add(mode)
        item["counts"][(model, mode)] += 1
        if row.get("status") == "produced":
            item["produced"] += 1
    result: dict[str, dict[str, Any]] = {}
    for case_id, item in evidence.items():
        paired_models = [
            model for model in item["models"]
            if item["counts"][(model, "linear")] and item["counts"][(model, "async")]
        ]
        minimum_repeats = min(
            [
                min(item["counts"][(model, "linear")], item["counts"][(model, "async")])
                for model in paired_models
            ] or [0]
        )
        result[case_id] = {
            "models": sorted(item["models"]),
            "modes": sorted(item["modes"]),
            "paired_models": sorted(paired_models),
            "minimum_paired_repetitions": minimum_repeats,
            "produced_episode_count": item["produced"],
        }
    return result


def _candidate_source_index(root: Path) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_root = root / "candidate_cases"
    if not candidate_root.is_dir():
        return {}
    for case_dir in sorted(path for path in candidate_root.iterdir() if path.is_dir()):
        public_path = case_dir / "public_case.yaml"
        if not public_path.is_file():
            continue
        public = yaml.safe_load(public_path.read_text(encoding="utf-8")) or {}
        simulation_only = (case_dir / "simulation_only.json").is_file()
        try:
            quality_errors = validate_case_quality(root, case_dir, require_contract=True)
        except (OSError, ValueError) as exc:
            # Incomplete candidate scaffolds stay in the index as failing quality,
            # they must not abort the whole audit.
            quality_errors = [f"incomplete candidate structure: {exc}"]
        complete = all((case_dir / path).is_file() for path in FORMAL_RUNTIME_FILES)
        case_ir_path = case_dir / "private/case_ir.json"
        score_plan_path = case_dir / "private/score_plan.json"
        causal_errors: list[str] = []
        if not case_ir_path.is_file() or not score_plan_path.is_file():
            causal_errors.append("missing task-causal Case IR or score plan")
        else:
            case_ir = _read_json(case_ir_path)
            score_plan = _read_json(score_plan_path)
            causal_errors.extend(validate_case_ir(case_ir))
            causal_errors.extend(validate_score_plan(score_plan))
            control_ids = {
                str(item.get("id") or "")
                for item in _checks(case_dir / "task/tests/control_flow_checks.json")
            }
            plan_ids = {str(item.get("id") or "") for item in score_plan.get("points") or []}
            if control_ids != plan_ids:
                causal_errors.append("score plan point ids differ from the runtime control registry")
        for source in public.get("source_tasks") or []:
            source_id = str(source.get("id") or "")
            if source_id:
                index[source_id].append({
                    "candidate_id": case_dir.name,
                    "complete_runtime_package": complete,
                    "quality_contract_passed": not quality_errors,
                    "task_causal_contract_passed": not causal_errors,
                    "task_causal_errors": causal_errors,
                    "simulation_only": simulation_only,
                })
    return dict(index)


def _generated_rows(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    v4_root = root / "artifacts/source-native-v4"
    unified_root = root / "artifacts/unified-case-set-v3/03-unified-production"
    v4 = _read_jsonl(v4_root / "native_manifest.jsonl")
    terminal = [
        row for row in _read_jsonl(unified_root / "case_manifest.jsonl")
        if str(row.get("benchmark")) == "Terminal-Bench"
    ]
    raw = [("source-native-v4", row) for row in v4] + [("unified-v3", row) for row in terminal]
    pilot = _pilot_evidence(root)
    candidates = _candidate_source_index(root)
    rows: list[dict[str, Any]] = []
    for collection, item in raw:
        case_id = str(item.get("case_id") or "")
        source_id = str(item.get("source_task_id") or "")
        benchmark = str(item.get("benchmark") or "")
        if collection == "source-native-v4":
            relative = str(item.get("native_path") or "")
            case_dir = v4_root / relative
        else:
            relative = str(item.get("path") or "")
            case_dir = unified_root / relative
        package = {
            "native_spec": (case_dir / "native_case.json").is_file(),
            "participant_task": (case_dir / "participant_task.json").is_file()
                or (case_dir / "task.md").is_file(),
            "public_case": (case_dir / "public_case.yaml").is_file(),
            "private_case": (case_dir / "private/private_case.yaml").is_file(),
            "dockerfile": (case_dir / "task/Dockerfile").is_file(),
            "semantic_registry": (case_dir / "task/tests/semantic_checks.json").is_file(),
            "control_registry": (case_dir / "task/tests/control_flow_checks.json").is_file(),
            "case_ir": (case_dir / "private/case_ir.json").is_file(),
            "score_plan": (case_dir / "private/score_plan.json").is_file(),
            "quality_contract": (case_dir / "private/quality_contract.yaml").is_file(),
        }
        model = pilot.get(case_id, {
            "models": [], "modes": [], "paired_models": [],
            "minimum_paired_repetitions": 0, "produced_episode_count": 0,
        })
        gates = {
            "runtime_ready": bool(item.get("runtime_ready")),
            "source_native_replay_ready": bool(item.get("source_native_replay_ready")),
            "formal_runtime_package": all(package[name] for name in (
                "public_case", "private_case", "dockerfile", "semantic_registry", "control_registry"
            )),
            "task_causal_ir_and_score_plan": package["case_ir"] and package["score_plan"],
            "quality_contract": package["quality_contract"],
            "explicit_async_classification": False,
            "minimum_empirical_pairing": (
                len(model["paired_models"]) >= 2 and model["minimum_paired_repetitions"] >= 3
            ),
            "formal_promotion_ready": bool(item.get("formal_promotion_ready")),
        }
        failed = [name for name, passed in gates.items() if not passed]
        if not gates["runtime_ready"]:
            disposition = "hold_missing_native_runtime"
        elif not gates["formal_runtime_package"]:
            disposition = "rebuild_task_specific_runtime_and_scoring"
        elif failed:
            disposition = "hold_failed_publication_gates"
        else:
            disposition = "strictly_selected"
        rows.append({
            "case_id": case_id,
            "benchmark": benchmark,
            "source_task_id": source_id,
            "source_collection": collection,
            "legacy_generation_family": item.get("family"),
            "primary_event_theme": None,
            "async_scenario_class": None,
            "capabilities": [],
            "runtime_blocker": item.get("runtime_blocker"),
            "package": package,
            "model_evidence": model,
            "related_rebuild_candidates": candidates.get(source_id, []),
            "gates": gates,
            "failed_gates": failed,
            "disposition": disposition,
        })
    ids = [row["case_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("generated case task inputs contain duplicate case_id values")
    return rows, {
        "input_count": len(rows),
        "source_native_v4_count": len(v4),
        "terminal_bench_unified_count": len(terminal),
        "strictly_selected_count": sum(row["disposition"] == "strictly_selected" for row in rows),
        "disposition_counts": dict(sorted(Counter(row["disposition"] for row in rows).items())),
        "benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in rows).items())),
        "async_classification_counts": {
            "formally_classified": sum(
                row["primary_event_theme"] in EVENT_THEMES
                and row["async_scenario_class"] in SCENARIO_CLASSES
                for row in rows
            ),
            "unclassified_generated_shell": sum(
                row["primary_event_theme"] is None
                or row["async_scenario_class"] is None
                for row in rows
            ),
        },
        "legacy_generation_family_counts": dict(sorted(Counter(
            str(row["legacy_generation_family"]) for row in rows
        ).items())),
    }


def build_strict_case_task_audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    registered_rows, registered_summary = _registered_rows(root)
    generated_rows, generated_summary = _generated_rows(root)
    technical_rebuilds = sorted({
        candidate["candidate_id"]
        for row in generated_rows
        for candidate in row["related_rebuild_candidates"]
        if candidate["complete_runtime_package"] and candidate["quality_contract_passed"]
        and candidate["task_causal_contract_passed"]
    })
    return {
        "schema_version": "1.0",
        "terminology": {
            "official_unit": "registered case task (case_id, instance_id)",
            "async_classification": "primary_event_theme + async_scenario_class + capabilities",
            "legacy_family_policy": "generation family is provenance only and is never an async classification",
        },
        "publication_rule": "fail_closed_all_static_runtime_scoring_review_and_empirical_gates",
        "registered_case_tasks": {
            "summary": registered_summary,
            "rows": registered_rows,
        },
        "generated_case_tasks": {
            "summary": generated_summary,
            "technically_complete_rebuild_candidates": technical_rebuilds,
            "rows": generated_rows,
        },
    }


def write_audit(audit: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
