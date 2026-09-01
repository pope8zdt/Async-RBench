"""Serialize a Codex-authored, API-free initial screen into a human-review queue."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402
from async_rbench.human_review import run_review_template  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(dossier: dict) -> tuple[list[int], str]:
    proposals = dossier.get("rule_proposals") or []
    if proposals:
        proposal = max(proposals, key=lambda row: len(row.get("evidence") or []))
        ids = [int(row["step_id"]) for row in proposal.get("evidence") or []]
        return list(dict.fromkeys(ids)), str(proposal.get("rule_event") or "")
    tail = dossier.get("tail") or []
    ids = [int(row["step_id"]) for row in tail[-2:] if row.get("step_id") is not None]
    return ids, ""


def _render(rows: list[dict], output: Path) -> None:
    output.write_text(f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Async-RBench Review Staging</title>
<style>body{{margin:0;background:#f3f5f8;color:#172033;font:14px/1.6 Arial,sans-serif}}main{{max-width:760px;margin:90px auto;background:#fff;border:1px solid #d9dee7;padding:42px}}h1{{font:600 27px Georgia,serif;color:#142b4a}}.tag{{letter-spacing:.12em;text-transform:uppercase;color:#637083;font-size:11px}}</style></head>
<body><main><div class="tag">Async-RBench · Review Protocol</div><h1>初筛完成，等待生成选择题复核工作台</h1>
<p>当前队列包含 {len(rows)} 条候选轨迹。人工复核页面由下一流水线阶段统一生成；该阶段只提供固定选项，并依据预注册规则自动计算结论，不接受自由文本。</p>
</main></body></html>""", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dossiers", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    dossier_path, policy_path = Path(args.dossiers).resolve(), Path(args.policy).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    dossiers = read_jsonl(dossier_path)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    families: dict[str, dict] = {}
    task_to_family: dict[str, dict] = {}
    for family in policy["families"]:
        families[family["id"]] = family
        for task in family["tasks"]:
            if task in task_to_family:
                raise ValueError(f"task occurs in multiple candidate families: {task}")
            task_to_family[task] = family
    watchlist = set(policy.get("watchlist_tasks") or []) - set(task_to_family)
    known = {str(row.get("task_name")) for row in dossiers}
    unknown = (set(task_to_family) | watchlist) - known
    if unknown:
        raise ValueError(f"policy contains tasks absent from dossier: {sorted(unknown)!r}")
    rows = []
    for dossier in dossiers:
        task = str(dossier.get("task_name") or "")
        family = task_to_family.get(task)
        evidence_ids, observed_event = _evidence(dossier)
        source_failure = str(dossier.get("source_failure") or "")
        no_reasoning = str(dossier.get("trajectory_format") or "").endswith("without_reasoning_trace")
        if source_failure:
            decision, transformability, family_id = "source_invalid", "not_assessable", "none"
            rationale = "The authoritative archive has no runnable trajectory payload; exclude it instead of treating an empty trace as a model failure."
        elif family and no_reasoning:
            decision, transformability, family_id = "needs_trace_expansion", "structurally_supported", family["id"]
            rationale = "The task has a credible async boundary, but this archive preserves terminal observations without agent reasoning; recover a richer trace before case production."
        elif family and dossier.get("rule_candidate_count", 0) > 0:
            decision, transformability, family_id = "promote_to_human", "supported", family["id"]
            rationale = "Codex found all four structural conditions and the trajectory contains an evidence-linked result/response boundary. Human review must verify the causal boundary, not the keyword hit."
        elif family:
            decision, transformability, family_id = "needs_trace_expansion", "structurally_supported", family["id"]
            rationale = "The task supports all four structural conditions, but the normalized trace lacks an explicit result-to-replan boundary; request richer evidence before promotion."
        elif task in watchlist:
            decision, transformability, family_id = "needs_trace_expansion", "uncertain", "watchlist"
            rationale = "Long-running or compatibility work may admit an async verifier, but the current evidence does not yet establish an arrival-order-dependent plan change."
        else:
            decision, transformability, family_id = "reject", "unsupported", "none"
            rationale = (
                "The rule hit is an ordinary sequential tool/test error and does not establish an independent result producer or arrival-order effect."
                if dossier.get("rule_candidate_count", 0) else
                "Codex found an atomic or sequential task with no evidenced independent producer whose late result changes already-started work."
            )
        spec = family or {}
        row = dict(dossier)
        row["codex_screen"] = {
            "status": "completed", "screening_mode": "codex_direct_no_external_api",
            "policy_version": policy["policy_version"], "decision": decision,
            "family": family_id,
            "trajectory_quality": "unusable" if source_failure else ("partial" if no_reasoning else "usable"),
            "failure_attribution": "source" if source_failure else "pending_human",
            "async_transformability": transformability,
            "candidate_event": str(spec.get("candidate_event") or observed_event),
            "evidence_step_ids": evidence_ids,
            "independent_producer": str(spec.get("independent_producer") or ""),
            "affected_work": str(spec.get("affected_work") or ""),
            "arrival_order_effect": str(spec.get("arrival_order_effect") or ""),
            "executable_consequence": str(spec.get("executable_consequence") or ""),
            "rationale": rationale,
        }
        row["human_review"] = run_review_template()
        rows.append(row)
    queue = [row for row in rows if row["codex_screen"]["decision"] in {"promote_to_human", "needs_trace_expansion"}]
    rejects = [row for row in rows if row["codex_screen"]["decision"] == "reject"]
    rng = random.Random(20260830)
    sample = sorted(rng.sample(rejects, min(len(rejects), max(20, len(rejects) // 10))), key=lambda row: row["review_id"])
    write_jsonl(output / "codex_labels.jsonl", rows)
    write_jsonl(output / "human_review_queue.jsonl", queue)
    write_jsonl(output / "rejection_audit_sample.jsonl", sample)
    write_jsonl(output / "source_failures.jsonl", [row for row in rows if row["codex_screen"]["decision"] == "source_invalid"])
    _render(queue, output / "human_review_workspace.html")
    report = {
        "policy_version": policy["policy_version"], "screening_mode": "codex_direct_no_external_api",
        "external_api_calls": 0, "input_count": len(rows),
        "decision_counts": dict(sorted(Counter(row["codex_screen"]["decision"] for row in rows).items())),
        "family_counts": dict(sorted(Counter(row["codex_screen"]["family"] for row in queue).items())),
        "human_review_queue_count": len(queue), "rejection_audit_sample_count": len(sample),
        "dossier_sha256": _sha256(dossier_path), "policy_sha256": _sha256(policy_path),
        "invariants": {
            "all_inputs_classified_once": len(rows) == len({row["review_id"] for row in rows}),
            "queue_is_strict_subset": {row["review_id"] for row in queue}.issubset({row["review_id"] for row in rows}),
            "source_failures_not_promoted": not any(row.get("source_failure") for row in queue),
        },
    }
    (output / "codex_screening_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
