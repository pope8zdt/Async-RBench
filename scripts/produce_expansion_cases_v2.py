"""Compile accepted reviews into stable, runnable, variable-point case capsules."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.authoritative_capsule import canonical_sha256  # noqa: E402
from async_rbench.expansion_case import (  # noqa: E402
    capsule_sha256,
    mutation_gate,
    oracle,
    oracle_gate,
    point_specs,
    react_oracle_gate,
)
from async_rbench.expansion_v2 import read_jsonl, stable_hash, write_json, write_jsonl  # noqa: E402


ORACLE_WRAPPER = """from pathlib import Path
import argparse,json,sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.expansion_case import oracle
p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['linear','async'],required=True); p.add_argument('--output',required=True); a=p.parse_args()
Path(a.output).write_text(json.dumps(oracle(Path(__file__).resolve().parent,a.mode),ensure_ascii=False,indent=2)+'\\n',encoding='utf-8')
"""


VERIFY_WRAPPER = """from pathlib import Path
import argparse,json,sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.expansion_case import verify_file
p=argparse.ArgumentParser(); p.add_argument('--submission',required=True); a=p.parse_args()
r=verify_file(Path(__file__).resolve().parent,Path(a.submission)); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['score']==1.0 else 1)
"""


REACT_ORACLE_WRAPPER = """from pathlib import Path
import json,sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.expansion_case import react_oracle_gate
r=react_oracle_gate(Path(__file__).resolve().parent); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['score']['score']==1.0 else 1)
"""


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:34] or "replan"


def _work(prefix: str, values: list[str]) -> list[dict[str, Any]]:
    return [
        {"id": f"{prefix}-{index:02d}-{stable_hash(value, length=6)}", "description": value}
        for index, value in enumerate(values, 1)
    ]


def _case_id(row: dict[str, Any]) -> str:
    benchmark = {"OSWorld": "osw", "SWE-bench": "swe", "MultiAgentBench": "mab"}[row["benchmark"]]
    family = _slug(str(row.get("semantic_family") or "replan"))
    return f"{benchmark}-{family}-{stable_hash(row['task_id'], row['candidate_id'], length=10)}"


def _full_source_instruction(source: dict[str, Any]) -> str:
    """Recover the authoritative instruction, not the clipped review excerpt."""
    payload = source.get("source_payload") or {}
    if source.get("benchmark") == "MultiAgentBench":
        task = payload.get("task") or {}
        value = task.get("content") or payload.get("task_content")
    else:
        value = payload.get("instruction")
    return str(value or source.get("instruction") or "")


def _task_markdown(public: dict[str, Any]) -> str:
    source = public["source"]
    return f"""# {public['case_id']}

## Source task

{source['instruction']}

## Controlled execution contract

Complete the source task while preserving any valid work already finished. An evaluator-controlled independent result is available before dependent work in `linear` mode and returns after unrelated work has begun in `async` mode. Integrate the payload, discard only the stale provisional work, complete all task-specific affected actions, and reverify the final state.

Submit one JSON object with `case_id`, `source_id`, `instruction_sha256`, `initial_plan`, `event_intake`, `revised_plan`, `final_action_ids`, and `closure`. The same mode-neutral outcome tests score Linear and Async; event-intake/replanning observations are reported separately as diagnostics. The public causal record is in `source_record.json`.
"""


def _compile(case_dir: Path, review: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    blueprint = review["case_blueprint"]
    case_id = _case_id(review)
    prior = _work("prior", list(blueprint["prior_valid_work"]))
    stale = _work("stale", list(blueprint["stale_work"]))
    affected = _work("required", list(blueprint["required_post_result_actions"]))
    event = {
        "id": f"event-{stable_hash(blueprint['delayed_result'], length=8)}",
        "description": blueprint["delayed_result"],
        "producer": "independent_subagent_or_environment",
        "authority": "authoritative_verifier",
    }
    preliminary_event = {
        "id": f"event-preliminary-{stable_hash(case_id, 'preliminary', length=8)}",
        "description": (
            "A fast subagent returns a preliminary recommendation: "
            + "; ".join(item["description"] for item in stale)
        ),
        "producer": "fast_independent_subagent",
        "authority": "provisional_unverified",
        "suggested_action_ids": [item["id"] for item in stale],
    }
    event["invalidates_event_id"] = preliminary_event["id"]
    instruction = _full_source_instruction(source)
    public = {
        "schema_version": "async-rbench-derived-capsule-v2",
        "case_id": case_id,
        "family": review["semantic_family"],
        "source": {
            "source_id": review["candidate_id"],
            "task_id": review["task_id"],
            "benchmark": review["benchmark"],
            "evidence_class": source.get("evidence_class"),
            "source_kind": source.get("source_kind"),
            "source_url": source.get("source_url"),
            "source_revision": source.get("source_revision"),
            "instruction": instruction,
            "instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
            "causal_origin": review["causal_origin"],
        },
        "causal_record": {
            "prior_work": prior,
            "independent_event": event,
            "event_sequence": [preliminary_event, event],
            "superseded_work": stale,
            "affected_work": affected,
            "async_stressor": blueprint["async_stressor"],
        },
        "scenarios": {
            "react": {"delivery": "blocking_before_dependent_work", "concurrency": 0},
            "linear": {"event_release_tick": 0, "concurrency": 0, "events_available": "authoritative_final"},
            "async": {"event_release_tick": 3, "concurrency": 2, "event_release_ticks": [1, 3]},
        },
        "review_binding": {
            "decision": review["decision"],
            "decision_counts": review["decision_counts"],
            "reviewer_type": "three_independent_codex_proxies_for_human",
            "selected_blueprint_reviewer": review["selected_blueprint_reviewer"],
        },
        "main_score_policy": "mode_neutral_task_outcome",
        "async_process_points_are_diagnostics_only": True,
    }
    expected = {
        "event_id": event["id"],
        "prior_work_ids": [row["id"] for row in prior],
        "affected_work_ids": [row["id"] for row in affected],
        "superseded_work_ids": [row["id"] for row in stale],
    }
    public["score_points"] = point_specs(public, expected)
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "private").mkdir(exist_ok=True)
    (case_dir / "case.json").write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (case_dir / "private" / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (case_dir / "private" / "review_evidence.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (case_dir / "source_record.json").write_text(json.dumps(public["causal_record"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (case_dir / "task.md").write_text(_task_markdown(public), encoding="utf-8")
    (case_dir / "oracle.py").write_text(ORACLE_WRAPPER, encoding="utf-8")
    (case_dir / "verify.py").write_text(VERIFY_WRAPPER, encoding="utf-8")
    (case_dir / "react_oracle.py").write_text(REACT_ORACLE_WRAPPER, encoding="utf-8")
    contract = {
        "schema_version": "preproduction-quality-contract-v2",
        "source_evidence_class": source.get("evidence_class"),
        "causal_origin": review["causal_origin"],
        "three_proxy_reviews": len(review.get("reviews") or []) == 3,
        "mode_neutral_main_score": True,
        "linear_baseline_reviewed_feasible": True,
        "score_points_derived_from_task_actions": len(affected),
        "full_source_instruction_restored_from_payload": True,
        "formal_registry_promotion": False,
        "promotion_blockers": ["model_pilot_not_yet_run", "formal_case_schema_not_yet_authored"],
    }
    write_json(case_dir / "private" / "preproduction_quality_contract.json", contract)
    return public


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = {str(row["candidate_id"]): row for row in read_jsonl(Path(args.candidates).resolve())}
    reviews = [row for row in read_jsonl(Path(args.reviews).resolve()) if row.get("eligible_for_production")]
    output = Path(args.output).resolve()
    cases_root = output / "cases"
    manifest = []
    all_mutations = []
    failures = []
    instruction_mismatches = []
    empty_instructions = []
    instruction_hashes: set[str] = set()
    semantic_hashes: Counter[str] = Counter()
    for review in reviews:
        candidate = source[str(review["candidate_id"])]
        case_id = _case_id(review)
        case_dir = cases_root / _slug(str(review["semantic_family"])) / case_id
        public = _compile(case_dir, review, candidate)
        expected_instruction = _full_source_instruction(candidate)
        actual_instruction = str(public["source"]["instruction"])
        if actual_instruction != expected_instruction:
            instruction_mismatches.append(case_id)
        if not actual_instruction.strip():
            empty_instructions.append(case_id)
        instruction_hashes.add(hashlib.sha256(actual_instruction.encode("utf-8")).hexdigest())
        semantic_hashes[canonical_sha256({
            "benchmark": public["source"]["benchmark"],
            "instruction": actual_instruction,
            "causal_record": public["causal_record"],
            "score_points": public["score_points"],
        })] += 1
        oracle_results = oracle_gate(case_dir)
        react_result = react_oracle_gate(case_dir)["score"]
        mutations = mutation_gate(case_dir)
        all_mutations.extend({"case_id": case_id, **row} for row in mutations)
        if any(result["score"] != 1.0 or result["unscored_point_count"] != 0 for result in oracle_results.values()):
            failures.append(f"{case_id}:oracle")
        if react_result["score"] != 1.0 or react_result["unscored_point_count"] != 0:
            failures.append(f"{case_id}:react_oracle")
        if any(not row["passed"] for row in mutations):
            failures.append(f"{case_id}:mutation")
        manifest.append({
            "case_id": case_id,
            "family": review["semantic_family"],
            "benchmark": review["benchmark"],
            "source_task_id": review["task_id"],
            "candidate_id": review["candidate_id"],
            "causal_origin": review["causal_origin"],
            "path": case_dir.relative_to(output).as_posix(),
            "score_point_count": len(public["score_points"]),
            "react_oracle_score": react_result["score"],
            "linear_oracle_score": oracle_results["linear"]["score"],
            "async_oracle_score": oracle_results["async"]["score"],
            "unscored_point_count": 0,
            "mutation_count": len(mutations),
            "capsule_sha256": capsule_sha256(case_dir),
        })
    duplicate_semantic_groups = sum(count > 1 for count in semantic_hashes.values())
    if instruction_mismatches:
        failures.append("batch:source_instruction_mismatch")
    if empty_instructions:
        failures.append("batch:empty_source_instruction")
    if duplicate_semantic_groups:
        failures.append("batch:duplicate_full_semantics")
    write_jsonl(output / "case_manifest.jsonl", manifest)
    write_jsonl(output / "mutation_results.jsonl", all_mutations)
    point_counts = [row["score_point_count"] for row in manifest]
    report = {
        "schema_version": "expansion-case-production-v2",
        "status": "passed" if not failures else "failed",
        "case_count": len(manifest),
        "unique_case_id_count": len({row["case_id"] for row in manifest}),
        "unique_source_task_count": len({(row["benchmark"], row["source_task_id"]) for row in manifest}),
        "source_instruction_mismatch_count": len(instruction_mismatches),
        "empty_source_instruction_count": len(empty_instructions),
        "distinct_source_instruction_count": len(instruction_hashes),
        "distinct_full_semantics_count": len(semantic_hashes),
        "duplicate_full_semantic_group_count": duplicate_semantic_groups,
        "benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in manifest).items())),
        "family_counts": dict(sorted(Counter(row["family"] for row in manifest).items())),
        "causal_origin_counts": dict(sorted(Counter(row["causal_origin"] for row in manifest).items())),
        "score_point_count_min": min(point_counts, default=0),
        "score_point_count_max": max(point_counts, default=0),
        "distinct_score_point_counts": sorted(set(point_counts)),
        "react_oracle_pass_count": sum(row["react_oracle_score"] == 1.0 for row in manifest),
        "linear_oracle_pass_count": sum(row["linear_oracle_score"] == 1.0 for row in manifest),
        "async_oracle_pass_count": sum(row["async_oracle_score"] == 1.0 for row in manifest),
        "mutation_checks_run": len(all_mutations),
        "mutation_failures": [row for row in all_mutations if not row["passed"]],
        "failures": failures,
        "formal_registry_promotion": False,
        "promotion_status": "runnable_preproduction_cases_pending_model_pilot_and_formal_schema",
    }
    write_json(output / "production_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
