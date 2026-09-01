"""Build compact, evidence-linked dossiers for direct Codex screening."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402


def _clip(value: object, limit: int) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--normalized-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    reviews = read_jsonl(Path(args.reviews).resolve())
    labels = {
        str(row.get("review_id") or ""): row
        for row in read_jsonl(Path(args.labels).resolve())
    }
    normalized: dict[str, dict] = {}
    for path in Path(args.normalized_dir).resolve().glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        normalized[str(row.get("review_id") or "")] = row
    dossiers = []
    for review in reviews:
        review_id = str(review.get("review_id") or "")
        normalized_path = str(review.get("normalized_trajectory") or "")
        trace = normalized.get(review_id) if normalized_path else None
        source_failure = "" if trace is not None else "normalization_failed_or_missing"
        trace = trace or {"steps": [], "result": {}}
        steps = trace.get("steps") or []
        by_id = {int(step["step_id"]): step for step in steps}
        task_step = next((step for step in steps if step.get("kind") == "task"), {})
        label = labels.get(review_id, {})
        proposals = []
        for candidate in label.get("candidate_decisions") or []:
            evidence_ids = []
            for field in (
                "precondition_step_ids", "trigger_step_ids", "response_step_ids",
                "consequence_step_ids",
            ):
                for step_id in candidate.get(field) or []:
                    if step_id not in evidence_ids:
                        evidence_ids.append(step_id)
            proposals.append({
                "rule_event": candidate.get("event_type"),
                "precondition_step_ids": candidate.get("precondition_step_ids") or [],
                "trigger_step_ids": candidate.get("trigger_step_ids") or [],
                "response_step_ids": candidate.get("response_step_ids") or [],
                "consequence_step_ids": candidate.get("consequence_step_ids") or [],
                "evidence": [
                    {
                        "step_id": step_id,
                        "role": by_id.get(step_id, {}).get("role"),
                        "kind": by_id.get(step_id, {}).get("kind"),
                        "content": _clip(
                            str(by_id.get(step_id, {}).get("content") or "") + " " +
                            str(by_id.get(step_id, {}).get("command") or ""),
                            700,
                        ),
                    }
                    for step_id in evidence_ids if step_id in by_id
                ],
            })
        dossiers.append({
            "review_id": review_id,
            "task_name": review.get("task_name"),
            "benchmark": (review.get("source") or {}).get("benchmark"),
            "source_agent": (review.get("source") or {}).get("agent"),
            "source_model": (review.get("source") or {}).get("model"),
            "manifest_solved": (review.get("machine_screen") or {}).get("manifest_solved"),
            "manifest_step_count": (review.get("machine_screen") or {}).get("step_count"),
            "normalized_step_count": len(steps),
            "trajectory_format": (trace.get("result") or {}).get("trajectory_format"),
            "source_failure": source_failure,
            "instruction": _clip(task_step.get("content") or (trace.get("result") or {}).get("instruction"), 1800),
            "rule_candidate_count": len(proposals),
            "rule_proposals": proposals,
            "tail": [
                {
                    "step_id": step.get("step_id"), "kind": step.get("kind"),
                    "content": _clip(str(step.get("content") or "") + " " + str(step.get("command") or ""), 500),
                }
                for step in steps[-4:]
            ],
            "codex_screen": {
                "status": "pending",
                "decision": "pending",
                "trajectory_quality": "pending",
                "failure_attribution": "pending",
                "async_transformability": "pending",
                "candidate_event": "",
                "evidence_step_ids": [],
                "independent_producer": "",
                "affected_work": "",
                "arrival_order_effect": "",
                "executable_consequence": "",
                "rationale": "",
            },
        })
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output, dossiers)
    print(f"dossiers={len(dossiers)} rule_positive={sum(row['rule_candidate_count'] > 0 for row in dossiers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
