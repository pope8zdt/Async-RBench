"""Run three independent fixed-choice Codex proxy reviews and adjudicate them."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.expansion_v2 import clip, read_jsonl, write_json, write_jsonl  # noqa: E402


LENSES = {
    "reviewer-a-causal": "You are a causal-inference methodologist. Be strict about independent production, temporal order, and whether the new result materially changes required work.",
    "reviewer-b-engineering": "You are a benchmark engineer. Be strict about deterministic executability, mode-neutral outcome scoring, mutation tests, and feasibility for a blocking ReAct baseline.",
    "reviewer-c-adversarial": "You are an adversarial dataset auditor. Try to disprove the proposed case, detect answer leakage, ordinary sequential feedback mislabeled as async, and benchmark/infrastructure confounds.",
}


PROMPT = """__LENS__

Act as one independent proxy for a human annotator. You have not seen the other reviewers. Complete only the fixed-choice fields from the supplied evidence, then propose a concise case blueprint when acceptance is justified.

Definitions:
- independent_result: produced by another agent/process/role, not the immediate return of the focal agent's own blocking action.
- pre_arrival_work: use "yes" only when observed. Use "designed" when the authoritative task contains a genuinely independent, delegable subtask (for example artifact extraction, repository analysis, test execution, specialist research, or one multi-agent role) and controlled delayed delivery preserves the original task meaning and outcome. The source benchmark need not originally run multiple agents; this benchmark deliberately introduces concurrent subagents into single-agent tasks.
- material_plan_delta: the payload changes which action/content/state is required, not merely that execution may continue.
- scoreable_consequence: required final artifacts/actions can be deterministically checked without judging prose style.
- linear_baseline_feasible: a blocking single-agent/ReAct execution can obtain the same information and complete the same outcome.

Decision is accept only when source_task_matches, independent_result, material_plan_delta, scoreable_consequence, and linear_baseline_feasible are yes; pre_arrival_work is yes or designed; leakage is not high; and evidence_sufficient is yes. A proposed subagent must return a task-specific payload that changes concrete downstream work; merely wrapping the focal agent's next blocking command is not independent. Use expand_evidence for a single genuinely missing fact. Otherwise reject.

Blueprint rules for accept: 1-4 prior valid work items, one concrete delayed result, 1-3 stale work items, and 2-7 task-specific post-result actions. Each item must describe an observable outcome, not a generic process slogan. For non-accept decisions return empty arrays/strings.

Return exactly one row per candidate, same order. Do not use tools.

RECORDS:
__RECORDS__
"""


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    screen = row.get("codex_semantic_screen") or {}
    return {
        "candidate_id": row["candidate_id"],
        "benchmark": row["benchmark"],
        "task_id": row["task_id"],
        "instruction": clip(row.get("instruction"), 1050),
        "features": row.get("features") or {},
        "semantic_screen": {
            key: screen.get(key) for key in (
                "evidence_quality", "causal_origin", "semantic_family",
                "evidence_refs", "rationale",
            )
        },
        "evidence_excerpt": [
            {**item, "content": clip(item.get("content"), 380)}
            for item in (row.get("evidence_excerpt") or [])
        ],
    }


def _run(
    reviewer: str,
    batch_index: int,
    batch: list[dict[str, Any]],
    output: Path,
    schema: Path,
    model: str,
    effort: str,
) -> tuple[str, int, list[dict[str, Any]], str]:
    reviewer_dir = output / reviewer
    reviewer_dir.mkdir(parents=True, exist_ok=True)
    result_path = reviewer_dir / f"batch-{batch_index:04d}.result.json"
    log_path = reviewer_dir / f"batch-{batch_index:04d}.stderr.log"
    expected = [str(row["candidate_id"]) for row in batch]
    if result_path.exists():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            reviews = list(payload.get("reviews") or [])
            if [str(row.get("candidate_id")) for row in reviews] == expected:
                return reviewer, batch_index, reviews, "cached"
        except (json.JSONDecodeError, OSError):
            pass
    prompt = PROMPT.replace("__LENS__", LENSES[reviewer]).replace(
        "__RECORDS__", json.dumps([_compact(row) for row in batch], ensure_ascii=False, indent=2),
    )
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        last = Path(handle.name)
    command = [
        "codex", "exec", "-", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--sandbox", "read-only", "--skip-git-repo-check", "-C", str(ROOT),
        "--model", model, "-c", f'model_reasoning_effort="{effort}"',
        "--output-schema", str(schema), "--output-last-message", str(last), "--color", "never",
    ]
    completed = subprocess.run(
        command, input=prompt, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=1800, check=False,
    )
    log_path.write_text(
        f"exit_code={completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        encoding="utf-8",
    )
    try:
        payload = json.loads(last.read_text(encoding="utf-8"))
        reviews = list(payload.get("reviews") or [])
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"{reviewer} batch {batch_index} invalid output; see {log_path}") from exc
    finally:
        last.unlink(missing_ok=True)
    if [str(row.get("candidate_id")) for row in reviews] != expected:
        raise RuntimeError(f"{reviewer} batch {batch_index} candidate id mismatch")
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return reviewer, batch_index, reviews, "completed"


def _validated_decision(review: dict[str, Any]) -> str:
    answers = review.get("answers") or {}
    required_yes = (
        "source_task_matches", "evidence_sufficient", "independent_result",
        "material_plan_delta", "scoreable_consequence", "linear_baseline_feasible",
    )
    if answers.get("answer_leakage") == "high" or any(answers.get(key) == "no" for key in required_yes):
        return "reject"
    if answers.get("pre_arrival_work") == "no":
        return "reject"
    blueprint = review.get("case_blueprint") or {}
    if (
        all(answers.get(key) == "yes" for key in required_yes)
        and answers.get("pre_arrival_work") in {"yes", "designed"}
        and answers.get("answer_leakage") in {"low", "medium"}
        and len(blueprint.get("required_post_result_actions") or []) >= 2
        and len(blueprint.get("prior_valid_work") or []) >= 1
        and len(blueprint.get("stale_work") or []) >= 1
        and str(blueprint.get("delayed_result") or "").strip()
    ):
        return "accept"
    if any(answers.get(key) == "uncertain" for key in required_yes) or answers.get("pre_arrival_work") == "uncertain":
        return "expand_evidence"
    return "reject"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--schema", default=str(ROOT / "schemas" / "codex_fixed_choice_review_v2.schema.json"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    rows = read_jsonl(Path(args.input).resolve())
    batches = [rows[index : index + args.batch_size] for index in range(0, len(rows), args.batch_size)]
    output = Path(args.output).resolve()
    schema = Path(args.schema).resolve()
    raw: dict[str, dict[int, list[dict[str, Any]]]] = {reviewer: {} for reviewer in LENSES}
    states: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(_run, reviewer, index, batch, output, schema, args.model, args.effort)
            for reviewer in LENSES for index, batch in enumerate(batches, 1)
        ]
        for future in as_completed(futures):
            reviewer, index, reviews, state = future.result()
            raw[reviewer][index] = reviews
            states[state] += 1
            print(f"{reviewer} batch {index}/{len(batches)} {state}", flush=True)

    by_reviewer: dict[str, list[dict[str, Any]]] = {}
    for reviewer in LENSES:
        reviewer_rows = [item for index in sorted(raw[reviewer]) for item in raw[reviewer][index]]
        for item in reviewer_rows:
            item["reviewer_id"] = reviewer
            item["reported_decision"] = item["decision"]
            item["decision"] = _validated_decision(item)
        by_reviewer[reviewer] = reviewer_rows
        write_jsonl(output / f"{reviewer}.reviews.jsonl", reviewer_rows)

    lookup = {
        reviewer: {str(item["candidate_id"]): item for item in items}
        for reviewer, items in by_reviewer.items()
    }
    source = {str(row["candidate_id"]): row for row in rows}
    adjudicated = []
    for candidate_id in source:
        reviews = [lookup[reviewer][candidate_id] for reviewer in LENSES]
        counts = Counter(review["decision"] for review in reviews)
        if counts["accept"] >= 2:
            decision = "accept"
        elif counts["reject"] >= 2:
            decision = "reject"
        else:
            decision = "expand_evidence"
        accepted_reviews = [review for review in reviews if review["decision"] == "accept"]
        preferred_order = ["reviewer-b-engineering", "reviewer-a-causal", "reviewer-c-adversarial"]
        blueprint_review = next(
            (lookup[name][candidate_id] for name in preferred_order if lookup[name][candidate_id] in accepted_reviews),
            None,
        )
        adjudicated.append({
            "candidate_id": candidate_id,
            "benchmark": source[candidate_id]["benchmark"],
            "task_id": source[candidate_id]["task_id"],
            "semantic_family": (source[candidate_id].get("codex_semantic_screen") or {}).get("semantic_family"),
            "causal_origin": (source[candidate_id].get("codex_semantic_screen") or {}).get("causal_origin"),
            "decision": decision,
            "eligible_for_production": decision == "accept",
            "decision_counts": dict(sorted(counts.items())),
            "unanimous": len(counts) == 1,
            "selected_blueprint_reviewer": blueprint_review.get("reviewer_id") if blueprint_review else None,
            "case_blueprint": blueprint_review.get("case_blueprint") if blueprint_review else None,
            "reviews": reviews,
            "reviewer_type": "codex_proxy_for_human",
        })
    write_jsonl(output / "adjudicated_reviews.jsonl", adjudicated)
    report = {
        "schema_version": "three-codex-proxy-review-v2",
        "candidate_count": len(rows),
        "review_count": len(rows) * len(LENSES),
        "reviewers": list(LENSES),
        "independent_invocations": True,
        "uses_external_api_key": False,
        "batch_states": dict(states),
        "adjudicated_decision_counts": dict(sorted(Counter(row["decision"] for row in adjudicated).items())),
        "production_eligible_count": sum(row["eligible_for_production"] for row in adjudicated),
        "unanimous_count": sum(row["unanimous"] for row in adjudicated),
        "benchmark_eligible_counts": dict(sorted(Counter(
            row["benchmark"] for row in adjudicated if row["eligible_for_production"]
        ).items())),
        "disclosure": "All three annotations were performed by separate gpt-5.6-sol invocations as a simulation of human fixed-choice review; they are not human labels.",
    }
    write_json(output / "proxy_review_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
