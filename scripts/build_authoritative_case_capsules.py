"""Compile reviewed authoritative records into runnable, source-derived case capsules."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.authoritative_capsule import (  # noqa: E402
    POINT_WEIGHTS,
    canonical_sha256,
    oracle_submission,
    score_submission,
)
from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402


PREFERRED_TERMINAL_TASKS = (
    "db-wal-recovery",
    "fix-code-vulnerability",
    "git-leak-recovery",
    "llm-inference-batching-scheduler",
    "multi-source-data-merger",
    "nginx-request-logging",
    "pytorch-model-recovery",
    "torch-pipeline-parallelism",
)


def _ref(step: dict) -> str:
    return str(step.get("source_ref") or f"step:{step.get('step_id')}")


def _work(step: dict) -> dict:
    return {
        "id": _ref(step),
        "kind": step.get("kind"),
        "app": step.get("app"),
        "function": step.get("function"),
        "description": str(step.get("content") or step.get("command") or "")[:1800],
    }


def _semantics(record: dict) -> dict:
    benchmark = str(record.get("benchmark") or "")
    steps = list(record.get("steps") or [])
    metadata = record.get("source_metadata") or {}
    if benchmark == "GAIA2":
        bridge = metadata.get("bridge") or {}
        by_suffix = {_ref(step).split(":", 1)[-1]: step for step in steps}
        prior = [by_suffix[value] for value in bridge.get("prior_event_ids") or [] if value in by_suffix]
        affected = [by_suffix[value] for value in bridge.get("affected_event_ids") or [] if value in by_suffix]
        late_id = str(bridge.get("late_event_id") or "")
        late = by_suffix.get(late_id)
    elif benchmark == "SentinelBench":
        observations = [step for step in steps if step.get("kind") == "observation"]
        target = int(metadata.get("target_event_index") or 0)
        late = observations[target] if target < len(observations) else observations[-1]
        prior = observations[:1]
        affected = [{
            "step_id": 900000 + target,
            "kind": "required_response",
            "source_ref": f"sentinel-response:{_ref(late)}",
            "content": f"Report the condition-bearing event after it arrives and close monitoring before kill_at={metadata.get('kill_at')}",
            "app": metadata.get("environment"),
            "function": "report_and_close",
        }]
    else:
        tail = list(record.get("tail") or [])
        evidence = list((record.get("codex_screen") or {}).get("evidence_step_ids") or [])
        late_step_id = evidence[-1] if evidence else (tail[-1].get("step_id") if tail else 2)
        late = next((step for step in tail if step.get("step_id") == late_step_id), None) or {
            "step_id": late_step_id, "kind": "observation",
            "source_ref": f"evidence:{late_step_id}",
            "content": (record.get("codex_screen") or {}).get("candidate_event") or "authoritative result",
        }
        prior_step = tail[0] if tail else {
            "step_id": evidence[0] if evidence else 1, "kind": "action",
            "source_ref": f"evidence:{evidence[0] if evidence else 1}",
            "content": "work completed before the delayed result",
        }
        prior = [prior_step]
        affected = [{
            "step_id": 900000 + int(late_step_id or 0), "kind": "required_response",
            "source_ref": f"required-response:{_ref(late)}",
            "content": str((record.get("codex_screen") or {}).get("affected_work") or "Revise affected work after the result")[:1800],
        }]
    if not prior or late is None or not affected:
        raise ValueError(f"record has incomplete causal semantics: {record.get('review_id')}")
    prior_work = [_work(step) for step in prior]
    affected_work = [_work(step) for step in affected]
    event = _work(late)
    return {
        "prior_work": prior_work,
        "event": event,
        "affected_work": affected_work,
        "superseded_work_ids": [f"provisional:{affected_work[0]['id']}"],
    }


def _task_markdown(public: dict) -> str:
    source = public["source"]
    return f"""# {public['case_id']}: asynchronous source-record integration

## Original source task

{source['instruction']}

## Executable capsule contract

Start the source task and record the work that can validly finish before an independent result arrives. The evaluator releases one authoritative event at tick 0 in `linear` mode and at tick 2 in `async` mode. Integrate that event without discarding unaffected work, invalidate the provisional event-dependent action, complete every affected action, and reverify closure.

Write one JSON submission containing: `case_id`, `source_id`, `instruction_sha256`, `initial_plan`, `event_intake`, `revised_plan`, `final_action_ids`, and `closure`. The public causal record is in `source_record.json`; the event feed is evaluator-controlled. Correctness is assessed by eight separately reported points. No preferred completion order is disclosed.
"""


ORACLE_WRAPPER = """from pathlib import Path
import argparse,json,sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.authoritative_capsule import oracle_submission
p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['linear','async'],required=True); p.add_argument('--output',required=True); a=p.parse_args()
Path(a.output).write_text(json.dumps(oracle_submission(Path(__file__).resolve().parent,a.mode),ensure_ascii=False,indent=2)+'\\n',encoding='utf-8')
"""


VERIFY_WRAPPER = """from pathlib import Path
import argparse,json,sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.authoritative_capsule import verify_submission_file
p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['linear','async'],required=True); p.add_argument('--submission',required=True); a=p.parse_args()
r=verify_submission_file(Path(__file__).resolve().parent,Path(a.submission),a.mode); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r['score']==1.0 else 1)
"""


def _write_capsule(case_dir: Path, case_id: str, family: str, record: dict, source_record: dict) -> dict:
    semantics = _semantics(source_record)
    instruction = str(source_record.get("instruction") or record.get("instruction") or "")
    public = {
        "schema_version": "authoritative-case-capsule-1",
        "case_id": case_id,
        "family": family,
        "source": {
            "source_id": record["internal_review_id"],
            "task_id": source_record.get("task_name"),
            "benchmark": source_record.get("benchmark"),
            "source_kind": source_record.get("source_kind") or source_record.get("trajectory_format"),
            "source_url": source_record.get("source_url"),
            "source_revision": source_record.get("source_revision"),
            "source_sha256": source_record.get("source_sha256"),
            "instruction": instruction,
            "instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
        },
        "causal_record": {
            "prior_work": semantics["prior_work"],
            "independent_event": semantics["event"],
            "affected_work": semantics["affected_work"],
        },
        "scenarios": {
            "linear": {"event_release_tick": 0},
            "async": {"event_release_tick": 2},
        },
        "score_points": [
            {"id": point_id, "weight": weight} for point_id, weight in POINT_WEIGHTS.items()
        ],
        "review_binding": {
            "stage1": "accept", "stage2": "accept",
            "reviewer_type": "codex_proxy_for_human",
        },
    }
    expected = {
        "event_id": semantics["event"]["id"],
        "prior_work_ids": [item["id"] for item in semantics["prior_work"]],
        "affected_work_ids": [item["id"] for item in semantics["affected_work"]],
        "superseded_work_ids": semantics["superseded_work_ids"],
    }
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "private").mkdir(exist_ok=True)
    (case_dir / "case.json").write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (case_dir / "source_record.json").write_text(json.dumps(public["causal_record"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (case_dir / "private" / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (case_dir / "task.md").write_text(_task_markdown(public), encoding="utf-8")
    (case_dir / "oracle.py").write_text(ORACLE_WRAPPER, encoding="utf-8")
    (case_dir / "verify.py").write_text(VERIFY_WRAPPER, encoding="utf-8")
    return public


def _select(adjudicated: list[dict], source_by_id: dict[str, dict], target: int) -> list[dict]:
    eligible = [row for row in adjudicated if row.get("eligible_for_production")]
    by_task: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        source = source_by_id[str(row["internal_review_id"])]
        by_task[str(source.get("task_name") or "")].append(row)
    selected = []
    for task_name, rows in sorted(by_task.items()):
        best = sorted(rows, key=lambda row: str(row["internal_review_id"]))[0]
        source = source_by_id[str(best["internal_review_id"])]
        if source.get("benchmark") in {"GAIA2", "SentinelBench"}:
            selected.append(best)
    preferred = []
    for task_name in PREFERRED_TERMINAL_TASKS:
        if task_name not in by_task:
            continue
        preferred.append(sorted(by_task[task_name], key=lambda row: str(row["internal_review_id"]))[0])
    seen_tasks = {
        str(source_by_id[str(row["internal_review_id"])].get("task_name")) for row in selected
    }
    for row in preferred:
        task = str(source_by_id[str(row["internal_review_id"])].get("task_name"))
        if task not in seen_tasks:
            selected.append(row); seen_tasks.add(task)
        if len(selected) >= target:
            break
    for task_name, rows in sorted(by_task.items()):
        if len(selected) >= target:
            break
        if task_name in seen_tasks:
            continue
        selected.append(sorted(rows, key=lambda row: str(row["internal_review_id"]))[0])
        seen_tasks.add(task_name)
    if len(selected) < target:
        raise ValueError(f"only {len(selected)} eligible unique tasks for target {target}")
    return selected[:target]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-collection", required=True)
    parser.add_argument("--source-queue", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target", type=int, default=300)
    args = parser.parse_args()
    collection = read_jsonl(Path(args.source_collection).resolve())
    queue = read_jsonl(Path(args.source_queue).resolve())
    source_by_id = {str(row["review_id"]): row for row in queue}
    source_by_id.update({str(row["review_id"]): row for row in collection})
    adjudicated = read_jsonl(Path(args.reviews).resolve())
    selected = _select(adjudicated, source_by_id, args.target)
    output = Path(args.output).resolve()
    cases_root = output / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)
    manifest = []
    scores = []
    mutation_failures = []
    for index, review in enumerate(selected, 1):
        case_id = f"authcase-{index:04d}"
        family = f"authoritative-replan-{(index - 1) % 6 + 1:02d}"
        source = source_by_id[str(review["internal_review_id"])]
        case_dir = cases_root / family / case_id
        public = _write_capsule(case_dir, case_id, family, review, source)
        mode_scores = {}
        for mode in ("linear", "async"):
            oracle = oracle_submission(case_dir, mode)
            result = score_submission(case_dir, oracle, mode)
            mode_scores[mode] = result["score"]
            scores.append(result)
            if result["score"] != 1.0 or result["unscored_point_count"] != 0:
                raise ValueError(f"oracle gate failed: {case_id}/{mode}: {result}")
        oracle = oracle_submission(case_dir, "async")
        for point_id in POINT_WEIGHTS:
            mutant = json.loads(json.dumps(oracle))
            if point_id == "source_identity": mutant["source_id"] = "wrong"
            elif point_id == "pre_event_work": mutant["initial_plan"]["completed_before_event"] = []
            elif point_id == "result_intake": mutant["event_intake"]["accepted"] = False
            elif point_id == "plan_revision": mutant["revised_plan"]["invalidated_work_ids"] = []
            elif point_id == "selective_preservation": mutant["revised_plan"]["preserved_work_ids"] = []
            elif point_id == "stale_rejection": mutant["final_action_ids"] += mutant["initial_plan"]["provisional_action_ids"]
            elif point_id == "affected_completion": mutant["final_action_ids"] = []
            elif point_id == "closure_reverification": mutant["closure"]["reverified"] = False
            mutant_score = score_submission(case_dir, mutant, "async")
            if mutant_score["checks"][point_id] or mutant_score["score"] >= 1.0:
                mutation_failures.append(f"{case_id}:{point_id}")
        manifest.append({
            "case_id": case_id,
            "family": family,
            "path": str(case_dir.relative_to(output)).replace("\\", "/"),
            "benchmark": public["source"]["benchmark"],
            "source_id": public["source"]["source_id"],
            "source_task_id": public["source"]["task_id"],
            "linear_oracle_score": mode_scores["linear"],
            "async_oracle_score": mode_scores["async"],
            "score_point_count": len(POINT_WEIGHTS),
            "unscored_point_count": 0,
            "capsule_sha256": canonical_sha256(public),
        })
    write_jsonl(output / "case_manifest.jsonl", manifest)
    report = {
        "schema_version": "authoritative-case-production-1",
        "status": "passed" if not mutation_failures else "failed",
        "case_count": len(manifest),
        "unique_source_task_count": len({row["source_task_id"] for row in manifest}),
        "benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in manifest).items())),
        "family_counts": dict(sorted(Counter(row["family"] for row in manifest).items())),
        "linear_oracle_pass_count": sum(row["linear_oracle_score"] == 1.0 for row in manifest),
        "async_oracle_pass_count": sum(row["async_oracle_score"] == 1.0 for row in manifest),
        "unscored_case_count": sum(row["unscored_point_count"] > 0 for row in manifest),
        "mutation_checks_run": len(manifest) * len(POINT_WEIGHTS),
        "mutation_failures": mutation_failures,
        "review_input": str(Path(args.reviews).resolve()),
        "case_manifest": str((output / "case_manifest.jsonl").resolve()),
        "promotion_status": "runnable_preproduction_capsules; full Async-RBench v2 promotion remains a separate gate",
    }
    (output / "production_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
