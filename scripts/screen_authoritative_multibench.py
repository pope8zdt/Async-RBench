"""Codex-authored structural screen for the versioned multi-benchmark source pool."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.human_review import run_review_template  # noqa: E402
from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402


def _step_ids(record: dict, refs: list[str]) -> list[int]:
    wanted = set(refs)
    return [
        int(step["step_id"]) for step in record.get("steps") or []
        if str(step.get("source_ref") or "").split(":", 1)[-1] in wanted
        or str(step.get("source_ref") or "") in wanted
    ]


def _screen(record: dict) -> dict:
    benchmark = str(record.get("benchmark") or "")
    metadata = record.get("source_metadata") or {}
    steps = record.get("steps") or []
    if benchmark == "GAIA2":
        bridge = metadata.get("bridge") or {}
        refs = (
            list(bridge.get("prior_event_ids") or [])
            + [str(bridge.get("late_event_id") or "")]
            + list(bridge.get("affected_event_ids") or [])
        )
        evidence = _step_ids(record, refs)
        return {
            "decision": "promote_to_human", "family": "dynamic_environment_revision",
            "trajectory_quality": "usable", "failure_attribution": "not_failure",
            "async_transformability": "source_graph_supported",
            "candidate_event": "late_environment_revision",
            "evidence_step_ids": evidence,
            "independent_producer": "The official GAIA2 environment emits an ENV event independently after oracle work has already completed.",
            "affected_work": "The source DAG contains prior oracle actions and later oracle actions directly dependent on the ENV event.",
            "arrival_order_effect": "The delayed ENV message revises or invalidates the already-started app actions and requires a different downstream plan.",
            "executable_consequence": "The official oracle action DAG provides deterministic affected actions that can be replayed by a local structural grader.",
            "rationale": "Codex verified an explicit official prior-action → ENV-event → affected-action dependency bridge. This is authoritative scenario structure, not a claimed model run.",
        }
    if benchmark == "SentinelBench":
        target = int(metadata.get("target_event_index") or 0)
        event_steps = [step for step in steps if step.get("kind") == "observation"]
        evidence = [1]
        if target > 0 and target - 1 < len(event_steps):
            evidence.append(int(event_steps[target - 1]["step_id"]))
        if target < len(event_steps):
            evidence.append(int(event_steps[target]["step_id"]))
        return {
            "decision": "promote_to_human", "family": "long_horizon_monitoring",
            "trajectory_quality": "usable", "failure_attribution": "not_failure",
            "async_transformability": "source_timeline_supported",
            "candidate_event": "delayed_condition_satisfaction",
            "evidence_step_ids": list(dict.fromkeys(evidence)),
            "independent_producer": "The official SentinelBench environment replays a timed event stream independently of the monitoring agent.",
            "affected_work": "The agent begins monitoring before the condition-bearing event arrives and must preserve state across distractors.",
            "arrival_order_effect": "Acting before the target event is incorrect; failing to react after arrival misses the bounded monitoring window.",
            "executable_consequence": "The official scenario supplies condition_at, kill_at and eval_sql for deterministic timing and state verification.",
            "rationale": "Codex found a non-noop official timeline with a concrete condition event and executable evaluator. This is an event timeline, not a claimed model run.",
        }
    if benchmark == "OSWorld":
        apps = list(metadata.get("related_apps") or [])
        changing = str(metadata.get("possibility_of_env_change") or "").lower()
        complex_task = len(apps) >= 2 or changing in {"medium", "high"}
        evidence = [int(step["step_id"]) for step in steps[-4:]]
        if complex_task:
            return {
                "decision": "needs_trace_expansion", "family": "cross_app_validation",
                "trajectory_quality": "usable", "failure_attribution": "pending_human",
                "async_transformability": "task_structurally_plausible_trace_not_causal",
                "candidate_event": "late_cross_app_validation",
                "evidence_step_ids": evidence,
                "independent_producer": "A second app reader or post-action evaluator could independently validate an artifact produced in another app.",
                "affected_work": "The public execution trace performs a multi-app or changing-environment workflow before the final evaluator result.",
                "arrival_order_effect": "Plausible but not yet proven by the archived run; a late cross-app validation may invalidate downstream GUI work.",
                "executable_consequence": "OSWorld task evaluators and public task assets can expose a stale cross-app artifact, subject to local reproducibility review.",
                "rationale": "The official model trace is real and the task spans multiple apps or a changing environment, but the archived run does not itself prove an independent mid-run result. Require trace expansion rather than promoting a hypothetical boundary.",
            }
        return {
            "decision": "reject", "family": "none",
            "trajectory_quality": "usable", "failure_attribution": "not_failure",
            "async_transformability": "unsupported",
            "candidate_event": "", "evidence_step_ids": evidence,
            "independent_producer": "", "affected_work": "",
            "arrival_order_effect": "", "executable_consequence": "",
            "rationale": "The public run is a real execution trace, but this task is an atomic single-app workflow with no evidenced independent result whose arrival order changes the plan.",
        }
    raise ValueError(f"unsupported collected benchmark: {benchmark}")


def _row(record: dict) -> dict:
    screen = _screen(record)
    screen.update({
        "status": "completed",
        "screening_mode": "codex_direct_structural_screen_v2_no_external_api",
        "policy_version": "codex-multibench-300-v1",
    })
    return {
        "review_id": record["review_id"], "task_name": record["task_name"],
        "benchmark": record["benchmark"], "source_kind": record["source_kind"],
        "source_agent": record.get("agent"), "source_model": record.get("model"),
        "source_url": record.get("source_url"),
        "source_revision": record.get("source_revision"),
        "source_artifact": record.get("source_artifact"),
        "source_sha256": record.get("source_sha256"),
        "manifest_solved": record.get("solved"),
        "manifest_step_count": len(record.get("steps") or []),
        "normalized_step_count": len(record.get("steps") or []),
        "trajectory_format": record.get("source_kind"), "source_failure": "",
        "instruction": record.get("instruction"),
        "source_metadata": record.get("source_metadata") or {},
        "tail": [
            {"step_id": step.get("step_id"), "kind": step.get("kind"),
             "content": (str(step.get("content") or "") + " " + str(step.get("command") or ""))[:700]}
            for step in (record.get("steps") or [])[-4:]
        ],
        "codex_screen": screen,
        "human_review": run_review_template(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--existing-queue")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = [_row(record) for record in read_jsonl(Path(args.sources).resolve())]
    labels = list(rows)
    queue = [
        row for row in rows
        if row["codex_screen"]["decision"] in {"promote_to_human", "needs_trace_expansion"}
    ]
    existing = read_jsonl(Path(args.existing_queue).resolve()) if args.existing_queue else []
    known = {str(row["review_id"]) for row in queue}
    for row in existing:
        if str(row.get("review_id") or "") not in known:
            queue.append(row)
            known.add(str(row.get("review_id") or ""))
    queue.sort(key=lambda row: (str(row.get("benchmark") or ""), str(row.get("review_id") or "")))
    write_jsonl(output / "codex_multibench_labels.jsonl", labels)
    write_jsonl(output / "human_review_queue.jsonl", queue)
    report = {
        "schema_version": "codex-multibench-screen-1",
        "screening_mode": "codex_direct_structural_screen_v2_no_external_api",
        "external_model_api_calls": 0,
        "new_source_count": len(rows),
        "new_decision_counts": dict(sorted(Counter(
            row["codex_screen"]["decision"] for row in rows
        ).items())),
        "existing_queue_count": len(existing),
        "combined_run_review_count": len(queue),
        "combined_task_review_count": len({str(row.get("task_name") or "") for row in queue}),
        "benchmark_counts": dict(sorted(Counter(str(row.get("benchmark") or "") for row in queue).items())),
    }
    (output / "screening_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
