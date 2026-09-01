"""Adjudicate two fine reviews and materialize one normalized 965-case collection."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.expansion_case import (  # noqa: E402
    capsule_sha256,
    mutation_gate,
    oracle_gate,
    point_specs,
    react_oracle_gate,
)
from async_rbench.unified_case_v3 import (  # noqa: E402
    FAMILIES,
    evidence_class,
    read_json,
    read_jsonl,
    stable_case_id,
)


ORACLE_SCRIPT = """from pathlib import Path
import argparse,json,sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.expansion_case import oracle
p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['linear','async'],required=True); p.add_argument('--output',required=True); a=p.parse_args()
Path(a.output).write_text(json.dumps(oracle(Path(__file__).resolve().parent,a.mode),ensure_ascii=False,indent=2)+'\\n',encoding='utf-8')
"""

VERIFY_SCRIPT = """from pathlib import Path
import argparse,json,sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.expansion_case import verify_file
p=argparse.ArgumentParser(); p.add_argument('--submission',required=True); a=p.parse_args()
r=verify_file(Path(__file__).resolve().parent,Path(a.submission)); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['score']==1.0 else 1)
"""

REACT_SCRIPT = """from pathlib import Path
import json,sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.expansion_case import react_oracle_gate
print(json.dumps(react_oracle_gate(Path(__file__).resolve().parent),ensure_ascii=False,indent=2))
"""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def review_map(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["unified_candidate_id"]): row for row in read_jsonl(path)}


def adjudicate(
    inventory: dict[str, Any], causal: dict[str, Any], engineering: dict[str, Any]
) -> dict[str, Any]:
    decisions = [str(causal["decision"]), str(engineering["decision"])]
    if decisions == ["keep_normalized", "keep_normalized"] and not inventory["fatal_issue_count"]:
        status = "keep_normalized"
    elif decisions == ["reject", "reject"]:
        status = "reject"
    else:
        status = "rebuild_required"
    families = [
        str(review.get("semantic_family") or "none")
        for review in (causal, engineering)
        if str(review.get("semantic_family") or "none") in FAMILIES
    ]
    if len(families) == 2 and families[0] == families[1]:
        family = families[0]
    elif str(engineering.get("semantic_family")) in FAMILIES:
        family = str(engineering["semantic_family"])
    elif families:
        family = families[0]
    else:
        family = str(inventory["current_family"])
    source_native = all(
        review.get("source_native_replay_ready") == "yes" for review in (causal, engineering)
    )
    formal_ready = status == "keep_normalized" and source_native
    return {
        "fine_screen_status": status,
        "semantic_family": family,
        "reviewer_decisions": {"causal": decisions[0], "engineering": decisions[1]},
        "reviewer_agreement": decisions[0] == decisions[1],
        "source_native_replay_ready": source_native,
        "formal_promotion_ready": formal_ready,
        "formal_blockers": [
            *([] if status == "keep_normalized" else ["fine_screen_not_kept"]),
            *([] if source_native else ["source_native_replay_missing"]),
            "empirical_async_challenge_not_case_validated",
        ],
    }


def normalize_public(
    original: dict[str, Any], expected: dict[str, Any], inventory: dict[str, Any],
    adjudication: dict[str, Any], causal_review: dict[str, Any], engineering_review: dict[str, Any],
) -> dict[str, Any]:
    collection = str(inventory["collection"])
    family = str(adjudication["semantic_family"])
    source = json.loads(json.dumps(original.get("source") or {}))
    repair = inventory.get("source_repair") or {}
    if repair:
        source["instruction"] = repair["instruction"]
        source["instruction_sha256"] = repair["instruction_sha256"]
        source["source_url"] = repair["source_url"]
        source["source_kind"] = repair["source_kind"]
        source["source_revision"] = repair["source_revision"]
        source["source_repair"] = {
            "method": repair["repair_method"],
            "replaced_instruction_sha256": repair["replaced_instruction_sha256"],
        }
    source["evidence_class"] = evidence_class(original, collection)
    source["causal_origin"] = (
        "observed_in_trace"
        if collection == "legacy-300" and (original.get("causal_record") or {}).get("independent_event", {}).get("kind") == "observation"
        else str(source.get("causal_origin") or "task_supported_injection")
    )
    causal = json.loads(json.dumps(original.get("causal_record") or {}))
    if not causal.get("superseded_work"):
        affected_by_id = {str(item.get("id")): item for item in causal.get("affected_work") or []}
        derived = []
        for index, stale_id in enumerate(expected.get("superseded_work_ids") or [], 1):
            base_id = str(stale_id).removeprefix("provisional:")
            base = affected_by_id.get(base_id) or {}
            derived.append({
                "id": str(stale_id),
                "description": "Provisional pre-authority variant of: " + str(base.get("description") or base_id),
                "migration_derived": True,
            })
        causal["superseded_work"] = derived
    if not causal.get("event_sequence"):
        event = json.loads(json.dumps(causal.get("independent_event") or {}))
        event.setdefault("producer", "independent_environment_or_trace_producer")
        event.setdefault("authority", "authoritative")
        causal["event_sequence"] = [event]
    normalized = {
        "schema_version": "async-rbench-unified-case-v3",
        "case_id": stable_case_id({**original, "source": source}, family),
        "family": family,
        "lineage": {
            "origin_collection": collection,
            "original_case_id": original.get("case_id"),
            "original_schema_version": original.get("schema_version"),
            "migration": "mechanical-normalization-with-audited-derived-stale-records",
        },
        "source": source,
        "causal_record": causal,
        "scenarios": {
            "react": {"delivery": "blocking_before_dependent_work", "concurrency": 0},
            "linear": {"event_release_tick": 0, "concurrency": 0, "events_available": "authoritative_final"},
            "async": {
                "event_release_tick": int((original.get("scenarios") or {}).get("async", {}).get("event_release_tick") or 2),
                "event_release_ticks": list((original.get("scenarios") or {}).get("async", {}).get("event_release_ticks") or [int((original.get("scenarios") or {}).get("async", {}).get("event_release_tick") or 2)]),
                "concurrency": max(2, int((original.get("scenarios") or {}).get("async", {}).get("concurrency") or 0)),
            },
        },
        "review_binding": {
            "decision": adjudication["fine_screen_status"],
            "reviewer_type": "two_independent_codex_fixed_choice_reviews",
            "reviewer_decisions": adjudication["reviewer_decisions"],
            "reviewer_agreement": adjudication["reviewer_agreement"],
        },
        "main_score_policy": "mode_neutral_task_outcome",
        "async_process_points_are_diagnostics_only": True,
        "quality_state": {
            **adjudication,
            "deterministic_issue_count": len(inventory.get("deterministic_issues") or []),
            "deterministic_issues": inventory.get("deterministic_issues") or [],
        },
    }
    normalized["score_points"] = point_specs(normalized, expected)
    return normalized


def task_markdown(public: dict[str, Any]) -> str:
    source = public["source"]
    causal = public["causal_record"]
    return (
        f"# {public['case_id']}\n\n"
        f"Source benchmark: {source.get('benchmark')}\n\n"
        f"## Original task\n\n{source.get('instruction')}\n\n"
        "## Controlled async treatment\n\n"
        f"{causal.get('async_stressor') or 'An independent result is delivered after useful prior work.'}\n\n"
        "The ReAct, Linear, and Async modes use the same final outcome score points. "
        "Async-only process diagnostics are not included in the main score.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", default="artifacts/unified-case-set-v3/00-inventory/unified_inventory_repaired.jsonl")
    parser.add_argument("--causal-reviews", default="artifacts/unified-case-set-v3/01-fine-review-causal-repaired/reviews.jsonl")
    parser.add_argument("--engineering-reviews", default="artifacts/unified-case-set-v3/02-fine-review-engineering-repaired/reviews.jsonl")
    parser.add_argument("--output", default="artifacts/unified-case-set-v3/03-unified-production")
    args = parser.parse_args()
    inventories = read_jsonl(Path(args.inventory).resolve())
    causal_reviews = review_map(Path(args.causal_reviews).resolve())
    engineering_reviews = review_map(Path(args.engineering_reviews).resolve())
    expected_ids = {str(row["unified_candidate_id"]) for row in inventories}
    if set(causal_reviews) != expected_ids or set(engineering_reviews) != expected_ids:
        raise RuntimeError("fine-review coverage is incomplete")
    output = Path(args.output).resolve()
    unified_schema = read_json(ROOT / "schemas" / "unified_case_v3.schema.json")
    manifest: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    mutation_rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for inventory in inventories:
        candidate_id = str(inventory["unified_candidate_id"])
        source_dir = Path(str(inventory["source_path"]))
        original = read_json(source_dir / "case.json")
        expected = read_json(source_dir / "private" / "expected.json")
        adjudication = adjudicate(inventory, causal_reviews[candidate_id], engineering_reviews[candidate_id])
        public = normalize_public(
            original, expected, inventory, adjudication,
            causal_reviews[candidate_id], engineering_reviews[candidate_id],
        )
        jsonschema.validate(public, unified_schema)
        case_dir = output / "cases" / public["family"].replace("_", "-") / public["case_id"]
        write_json(case_dir / "case.json", public)
        write_json(case_dir / "source_record.json", public["causal_record"])
        write_json(case_dir / "private" / "expected.json", expected)
        write_json(case_dir / "private" / "fine_review.json", {
            "deterministic_issues": inventory["deterministic_issues"],
            "causal_review": causal_reviews[candidate_id],
            "engineering_review": engineering_reviews[candidate_id],
            "adjudication": adjudication,
        })
        (case_dir / "task.md").write_text(task_markdown(public), encoding="utf-8")
        (case_dir / "oracle.py").write_text(ORACLE_SCRIPT, encoding="utf-8")
        (case_dir / "verify.py").write_text(VERIFY_SCRIPT, encoding="utf-8")
        (case_dir / "react_oracle.py").write_text(REACT_SCRIPT, encoding="utf-8")
        gates = oracle_gate(case_dir)
        react = react_oracle_gate(case_dir)
        mutations = mutation_gate(case_dir)
        mutation_rows.extend({"case_id": public["case_id"], **row} for row in mutations)
        if any(gates[mode]["score"] != 1.0 or gates[mode]["unscored_point_count"] for mode in ("linear", "async")):
            failures.append(f"{public['case_id']}: linear/async oracle failure")
        if react["score"]["score"] != 1.0 or react["score"]["unscored_point_count"]:
            failures.append(f"{public['case_id']}: react oracle failure")
        if not all(row["passed"] for row in mutations):
            failures.append(f"{public['case_id']}: mutation escape")
        record = {
            "case_id": public["case_id"],
            "path": str(case_dir.relative_to(output)).replace("\\", "/"),
            "family": public["family"],
            "benchmark": public["source"].get("benchmark"),
            "source_task_id": public["source"].get("task_id"),
            "origin_collection": inventory["collection"],
            "original_case_id": inventory["original_case_id"],
            "fine_screen_status": adjudication["fine_screen_status"],
            "source_native_replay_ready": adjudication["source_native_replay_ready"],
            "formal_promotion_ready": adjudication["formal_promotion_ready"],
            "score_point_count": len(public["score_points"]),
            "react_oracle_score": react["score"]["score"],
            "linear_oracle_score": gates["linear"]["score"],
            "async_oracle_score": gates["async"]["score"],
            "mutation_count": len(mutations),
            "capsule_sha256": capsule_sha256(case_dir),
        }
        manifest.append(record)
        audit_rows.append({
            **record,
            "deterministic_issues": inventory["deterministic_issues"],
            "causal_review": causal_reviews[candidate_id],
            "engineering_review": engineering_reviews[candidate_id],
        })
    manifest.sort(key=lambda row: row["case_id"])
    audit_rows.sort(key=lambda row: row["case_id"])
    write_jsonl(output / "case_manifest.jsonl", manifest)
    write_jsonl(output / "fine_screen_audit.jsonl", audit_rows)
    write_jsonl(output / "mutation_results.jsonl", mutation_rows)
    status_counts = Counter(row["fine_screen_status"] for row in manifest)
    report = {
        "schema_version": "async-rbench-unified-production-v3",
        "status": "passed" if not failures else "failed",
        "case_count": len(manifest),
        "origin_collection_counts": dict(sorted(Counter(row["origin_collection"] for row in manifest).items())),
        "benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in manifest).items())),
        "family_counts": dict(sorted(Counter(row["family"] for row in manifest).items())),
        "fine_screen_status_counts": dict(sorted(status_counts.items())),
        "fine_screen_by_origin": {
            origin: dict(sorted(Counter(row["fine_screen_status"] for row in rows).items()))
            for origin, rows in sorted(
                ((origin, [row for row in manifest if row["origin_collection"] == origin])
                 for origin in {row["origin_collection"] for row in manifest}),
                key=lambda item: item[0],
            )
        },
        "reviewer_agreement_count": sum(
            row["causal_review"]["decision"] == row["engineering_review"]["decision"]
            for row in audit_rows
        ),
        "source_native_replay_ready_count": sum(row["source_native_replay_ready"] for row in manifest),
        "formal_promotion_ready_count": sum(row["formal_promotion_ready"] for row in manifest),
        "score_point_count_distribution": dict(sorted(Counter(row["score_point_count"] for row in manifest).items())),
        "react_oracle_pass_count": sum(row["react_oracle_score"] == 1.0 for row in manifest),
        "linear_oracle_pass_count": sum(row["linear_oracle_score"] == 1.0 for row in manifest),
        "async_oracle_pass_count": sum(row["async_oracle_score"] == 1.0 for row in manifest),
        "mutation_checks_run": len(mutation_rows),
        "mutation_escape_count": sum(not row["passed"] for row in mutation_rows),
        "failures": failures,
    }
    write_json(output / "production_report.json", report)
    write_jsonl(output / "keep_manifest.jsonl", [row for row in manifest if row["fine_screen_status"] == "keep_normalized"])
    write_jsonl(output / "rebuild_manifest.jsonl", [row for row in manifest if row["fine_screen_status"] == "rebuild_required"])
    write_jsonl(output / "reject_manifest.jsonl", [row for row in manifest if row["fine_screen_status"] == "reject"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
