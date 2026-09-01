from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "candidate_cases" / "rebuild-to-100" / "selection-manifest.json"
AUDIT = ROOT / "artifacts" / "case-transformability-audit-v2" / "cases.jsonl"
DEFAULT_OUTPUT = ROOT / "candidate_cases" / "rebuild-to-100" / "blueprints"


EVENT_POLICIES: dict[str, dict[str, Any]] = {
    "delayed_authoritative_result": {
        "authority_rule": "Only the delayed evaluator-owned result can close the affected requirement.",
        "required_decisions": ["wait_for_authority", "revise_affected_state", "reverify_closure"],
        "forbidden_shortcut": "Do not infer authority from completion order or a provisional result.",
    },
    "late_or_out_of_order_superseded_result": {
        "authority_rule": "The newest valid authority supersedes the earlier result for the affected closure only.",
        "required_decisions": ["identify_supersession", "reject_stale_result", "selective_replan"],
        "forbidden_shortcut": "Do not retain or merge a displaced result merely because it arrived first.",
    },
    "partial_then_complete_result": {
        "authority_rule": "Partial evidence may inform provisional work but cannot close the complete-result contract.",
        "required_decisions": ["classify_partial_scope", "adopt_completion_delta", "reverify_closure"],
        "forbidden_shortcut": "Do not treat partial evidence as a complete authoritative result.",
    },
    "conflicting_valid_results": {
        "authority_rule": "Resolve the conflict using task evidence and declared authority, preserving valid non-conflicting work.",
        "required_decisions": ["classify_conflict", "arbitrate_evidence", "replan_affected_scope"],
        "forbidden_shortcut": "Do not select a result by arrival order or invalidate all prior work.",
    },
    "duplicate_or_replayed_completion": {
        "authority_rule": "A replay of an already consumed completion is idempotent and must not repeat side effects.",
        "required_decisions": ["detect_replay", "deduplicate_completion", "confirm_idempotent_closure"],
        "forbidden_shortcut": "Do not apply the same completion twice or create duplicate artifacts.",
    },
    "child_failure_or_implicit_error": {
        "authority_rule": "An absent or failed child result is an explicit state transition requiring scoped recovery.",
        "required_decisions": ["surface_failure", "recover_or_redelegate", "close_with_failure_evidence"],
        "forbidden_shortcut": "Do not interpret silence, timeout, or malformed output as successful completion.",
    },
    "task_scope_or_dependency_change": {
        "authority_rule": "The live scope delta changes only its dependency closure and preserves unaffected commitments.",
        "required_decisions": ["classify_scope_delta", "invalidate_affected_scope", "reverify_dependency_closure"],
        "forbidden_shortcut": "Do not ignore the scope change or restart unaffected work.",
    },
    "straggler_under_resource_pressure": {
        "authority_rule": "Resource evidence determines critical-path triage without sacrificing required preserved work.",
        "required_decisions": ["classify_critical_path", "triage_resource_budget", "reverify_required_outcomes"],
        "forbidden_shortcut": "Do not wait indefinitely or cancel work outside the affected resource closure.",
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.replace("\r\n", "\n"), encoding="utf-8")


def _audit_rows() -> dict[str, dict[str, Any]]:
    return {
        row["case_id"]: row
        for row in (
            json.loads(line)
            for line in AUDIT.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _participant_task(row: dict[str, Any]) -> tuple[dict[str, Any], str, Path]:
    source = next(
        ROOT / value
        for value in row["source_audit"]["source_files"]
        if value.endswith("participant_task.json")
    )
    payload = _read_json(source)
    if isinstance(payload.get("problem_statement"), str):
        instruction = payload["problem_statement"]
    elif isinstance(payload.get("instruction"), str):
        instruction = payload["instruction"]
    else:
        instruction = str((payload.get("task") or {}).get("content") or "").strip()
    if not instruction:
        raise ValueError(f"{row['case_id']}: participant instruction is empty")
    return payload, instruction, source


def _instruction(row: dict[str, Any], source_instruction: str) -> str:
    return (
        source_instruction.rstrip()
        + "\n\nASYNC-RBENCH EXTENSION\n"
        + "During the task, the harness may deliver independently produced evidence. "
        + "Treat a delivered receipt as new evidence rather than as an answer. Reassess "
        + "only the work actually affected by that evidence, preserve still-valid work, "
        + "and verify the final task outcome. Runtime event details are intentionally not "
        + "disclosed in advance.\n"
    )


def _workstreams(row: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    streams: list[dict[str, Any]] = []
    bindings: dict[str, Any] = {}
    for index, requirement in enumerate(row["case_ir_blueprint"]["task_requirements"], 1):
        stream_id = f"requirement_{index:02d}"
        report = f"/app/output_data/workstreams/{stream_id}.json"
        schema = {
            "report_path": {"type": "string", "const": report},
            "requirement_id": {"type": "string", "const": requirement["id"]},
            "workspace_revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "finding": {"type": "string", "minLength": 1},
        }
        streams.append(
            {
                "id": stream_id,
                "task": requirement["description"],
                "targets": ["final_state"],
                "expected_output": requirement["public_evidence"],
                "priority": "high" if index == 1 else "normal",
                "required_evidence_fields": list(schema),
                "evidence_schema": schema,
                "allowed_files": [report],
                "required_files": [report],
                "public_result_contract": {"requirement_id": requirement["id"]},
            }
        )
        bindings[stream_id] = {
            "result_kind": f"requirement_result_{index:02d}",
            "private_evidence_schema": schema,
            "validator": "source_native_adapter",
            "event_assets": [] if index < len(row["case_ir_blueprint"]["task_requirements"]) else ["private/event_policy.json"],
        }
    return streams, bindings


def _copy_source_manifests(row: dict[str, Any], case_dir: Path, participant_path: Path) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []
    private_root = case_dir / "private" / "source_manifests"
    for index, relative in enumerate(row["source_audit"]["source_files"], 1):
        source = ROOT / relative
        if source.resolve() == participant_path.resolve():
            continue
        destination = private_root / f"{index:02d}-{source.name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(
            {
                "source": relative,
                "private_copy": str(destination.relative_to(case_dir)).replace("\\", "/"),
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            }
        )
    return copied


def materialize(row: dict[str, Any], output_root: Path) -> dict[str, Any]:
    case_id = str(row["case_id"])
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{case_id}.", dir=output_root))
    target = output_root / case_id
    try:
        participant, source_instruction, participant_path = _participant_task(row)
        full_instruction = _instruction(row, source_instruction)
        streams, bindings = _workstreams(row)
        classification = row["async_classification_plan"]
        event = row["case_ir_blueprint"]["event_contract"]
        policy = EVENT_POLICIES[classification["primary_event_theme"]]
        _write_text(temporary / "instruction.md", full_instruction)
        _write_json(temporary / "task" / "task_file" / "participant_task.json", participant)
        _write_json(
            temporary / "task" / "task_file" / "async_contract.json",
            {
                "case_id": case_id,
                "protocol": "runtime_receipt_v1",
                "required_evidence": [item["required_files"][0] for item in streams],
                "participant_visible_event_fields": ["receipt_id", "result_kind", "released_at", "evidence"],
            },
        )
        _write_json(
            temporary / "task" / "task.yaml",
            {
                "instruction": full_instruction,
                "author_name": "Async-RBench individualized rebuild",
                "difficulty": "pending_native_calibration",
                "category": row["benchmark"],
                "tags": [classification["primary_event_theme"], classification["async_scenario_class"]],
                "runtime_status": "pending_source_native_implementation",
            },
        )
        _write_json(
            temporary / "public_case.yaml",
            {
                "format_version": 2,
                "case_id": case_id,
                "title": f"Async-RBench individualized rebuild: {row['source_task_id']}",
                "task_instruction_path": "task/task.yaml",
                "source_tasks": [{"id": row["source_task_id"], "benchmark": row["benchmark"]}],
                "milestones": row["case_ir_blueprint"]["dependency_graph"]["nodes"],
                "artifacts": [
                    {"id": "preserve_prior", "path": "/app/output_data/preserved_state.json"},
                    {"id": "final_state", "path": "/app/output_data/final_state.json"},
                ],
                "workstreams": streams,
                "public_checks": [],
            },
        )
        _write_json(
            temporary / "private" / "private_case.yaml",
            {
                "format_version": 2,
                "case_id": case_id,
                "classification": {
                    "primary_event_theme": classification["primary_event_theme"],
                    "secondary_event_themes": classification.get("secondary_event_themes") or [],
                    "async_scenario_class": classification["async_scenario_class"],
                },
                "capabilities": classification["capabilities"],
                "workstream_bindings": bindings,
                "event_contracts": [event],
                "scenarios": {"linear": {"events": []}, "async": {"events": [{"id": event["event_id"], "private": True}]}},
                # Runtime plans describe the hidden-test strategy as prose.
                # Executable observer commands are authored by the source
                # adapter later; never coerce that prose into this mapping.
                "artifact_observers": {},
                "information_sufficiency": [
                    {
                        "workstream_id": item["id"],
                        "public_inputs": ["task/task.yaml", "public_case.yaml"],
                        "required_output_fields": item["required_evidence_fields"],
                        "review_status": "blueprint_reviewed_runtime_pending",
                    }
                    for item in streams
                ],
            },
        )
        _write_json(temporary / "private" / "case_ir.json", row["case_ir_blueprint"])
        _write_json(
            temporary / "private" / "score_plan.json",
            {"semantic_points": row["semantic_score_blueprint"], "control_points": row["control_score_blueprint"], "negative_mutations": row["negative_mutation_blueprint"]},
        )
        _write_json(temporary / "private" / "dynamic_point_plan.json", {"version": "7", "checks": row["control_score_blueprint"]})
        _write_json(temporary / "private" / "runtime_contract.json", row["runtime_package_plan"])
        _write_json(temporary / "private" / "source_lock.json", row["source_audit"])
        _write_json(
            temporary / "private" / "event_policy.json",
            {"event_id": event["event_id"], "theme": classification["primary_event_theme"], **policy, "event_contract": event},
        )
        source_manifest = _copy_source_manifests(row, temporary, participant_path)
        _write_json(
            temporary / "private" / "source_adapter.json",
            {
                "benchmark": row["benchmark"],
                "source_task_id": row["source_task_id"],
                "runtime_plan": row["runtime_package_plan"],
                "private_source_manifests": source_manifest,
                "participant_source": "task/task_file/participant_task.json",
            },
        )
        _write_json(
            temporary / "private" / "quality_contract.yaml",
            {
                "schema_version": "1",
                "publication_eligible": False,
                "semantic_checks": [item["id"] for item in row["semantic_score_blueprint"]],
                "dynamic_control_checks": [item["id"] for item in row["control_score_blueprint"]],
                "negative_mutations": row["negative_mutation_blueprint"],
                "pending_gates": ["source_native_runtime", "canonical_oracle", "equivalent_solution", "executed_mutations", "human_approval", "multi_model_calibration"],
            },
        )
        _write_json(temporary / "mutation_families.json", {"version": "blueprint-v1", "mutations": row["negative_mutation_blueprint"]})
        _write_json(
            temporary / "STATUS.json",
            {
                "case_id": case_id,
                "status": "blueprint_materialized_pending_source_native_implementation",
                "registered": False,
                "runtime_executed": False,
                "quality_execution_passed": False,
                "semantic_point_count": len(row["semantic_score_blueprint"]),
                "control_point_count": len(row["control_score_blueprint"]),
            },
        )
        _write_text(
            temporary / "PROVENANCE.md",
            f"# {case_id}\n\nSource: `{row['benchmark']}` / `{row['source_task_id']}`.\n\nPrimary event: `{classification['primary_event_theme']}`.\n\nThe individualized blueprint contract is materialized. Source-native execution and promotion remain pending.\n",
        )
        if target.exists():
            shutil.rmtree(target)
        temporary.replace(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "case_id": case_id,
        "benchmark": row["benchmark"],
        "primary_event_theme": classification["primary_event_theme"],
        "semantic_points": len(row["semantic_score_blueprint"]),
        "control_points": len(row["control_score_blueprint"]),
        "status": "pending_source_native_implementation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, default=SELECTION)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--shard", type=int, choices=(1, 2, 3))
    parser.add_argument("--case-id", action="append")
    args = parser.parse_args()
    selection = _read_json(args.selection)
    selected_ids = set(args.case_id or [])
    items = [
        item for item in selection["cases"]
        if (args.shard is None or item["shard"] == args.shard)
        and (not selected_ids or item["case_id"] in selected_ids)
    ]
    rows = _audit_rows()
    results = [materialize(rows[item["case_id"]], args.output_root) for item in items]
    shard_name = f"shard-{args.shard}" if args.shard else "all"
    manifest = {
        "schema_version": "async-rbench-blueprint-materialization-v1",
        "shard": args.shard,
        "case_count": len(results),
        "cases": results,
        "registry_mutated": False,
        "runtime_claimed": False,
    }
    _write_json(args.output_root / f"manifest-{shard_name}.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
