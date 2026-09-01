"""Use the logged-in Codex account for evidence-grounded semantic screening."""

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


PROMPT = """You are the semantic screening stage for an academic benchmark about agent replanning when independent subagent results arrive asynchronously. Review EVERY supplied record independently. Do not use tools and do not infer facts absent from the evidence.

The benchmark needs cases where the same task outcome is feasible for a blocking single-agent baseline, but a concurrent harness must preserve valid prior work, integrate a newly arrived independent result, invalidate only stale work, and finish the affected task. Ordinary sequential command output, a normal error/retry, or a test result immediately requested by the same action is NOT an observed asynchronous boundary.

causal_origin rules:
- observed_in_trace: the evidence itself shows independent production plus pre-arrival work and a causally changed response.
- task_supported_injection: the authoritative task has a genuinely delegable subproblem whose concrete payload is needed by downstream work, so a controlled delayed subagent result can be introduced without changing the original task's meaning or final outcome. The source trace may be single-agent: this benchmark deliberately transforms OSWorld/SWE-bench tasks into concurrent-subagent executions. Examples include extracting values from another artifact while drafting a report, repository/API analysis while an implementation starts, an independent test/reproduction result that changes the patch, or one specialist role in MultiAgentBench. Never claim the injection was observed in the source trace.
- unsupported: neither condition holds.

Decision rules:
- promote_to_review only when independent_result_candidate=yes, executable_outcome_scoreable=yes, answer leakage is not high, and causal_origin is observed_in_trace or task_supported_injection. For task-supported injection, "independent_result_candidate=yes" means the proposed subproblem can actually be delegated and return a task-specific payload; it does not require the original trace to contain a second agent.
- expand_evidence when the task looks plausible but one required fact is uncertain or only a final output is present.
- reject ordinary sequential feedback when it cannot be externalized into a genuine subproblem, non-causal errors, unusable evidence, or tasks where the proposed payload would not materially change downstream content/actions. Do not promote merely by renaming the focal agent's next blocking command as a subagent.

Evidence refs must cite supplied step_id values or feature names. Keep rationale concrete and under 120 words. Return exactly one review for each candidate_id, in the same order.

RECORDS:
__RECORDS__
"""


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row["candidate_id"],
        "benchmark": row["benchmark"],
        "task_id": row["task_id"],
        "evidence_class": row["evidence_class"],
        "instruction": clip(row.get("instruction"), 1100),
        "features": row.get("features") or {},
        "evidence_excerpt": [
            {
                "step_id": item.get("step_id"),
                "role": item.get("role"),
                "kind": item.get("kind"),
                "content": clip(item.get("content"), 420),
            }
            for item in (row.get("evidence_excerpt") or [])
        ],
    }


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _run_batch(
    index: int,
    batch: list[dict[str, Any]],
    output: Path,
    schema: Path,
    model: str,
    effort: str,
) -> tuple[int, list[dict[str, Any]], str]:
    batch_dir = output / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    result_path = batch_dir / f"batch-{index:04d}.result.json"
    log_path = batch_dir / f"batch-{index:04d}.stderr.log"
    input_path = batch_dir / f"batch-{index:04d}.input.json"
    expected = [str(row["candidate_id"]) for row in batch]
    input_path.write_text(json.dumps([_compact(row) for row in batch], ensure_ascii=False, indent=2), encoding="utf-8")
    if result_path.exists():
        try:
            cached = json.loads(result_path.read_text(encoding="utf-8"))
            reviews = list(cached.get("reviews") or [])
            if [str(item.get("candidate_id")) for item in reviews] == expected:
                return index, reviews, "cached"
        except (json.JSONDecodeError, OSError):
            pass
    prompt = PROMPT.replace("__RECORDS__", input_path.read_text(encoding="utf-8"))
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        last_message = Path(handle.name)
    command = [
        "codex", "exec", "-", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--sandbox", "read-only", "--skip-git-repo-check", "-C", str(ROOT),
        "--model", model, "-c", f'model_reasoning_effort="{effort}"',
        "--output-schema", str(schema), "--output-last-message", str(last_message),
        "--color", "never",
    ]
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=900,
        check=False,
    )
    log_path.write_text(
        f"exit_code={completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        encoding="utf-8",
    )
    try:
        payload = json.loads(last_message.read_text(encoding="utf-8"))
        reviews = list(payload.get("reviews") or [])
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"batch {index} produced invalid JSON: {exc}; see {log_path}") from exc
    finally:
        last_message.unlink(missing_ok=True)
    ids = [str(item.get("candidate_id")) for item in reviews]
    if ids != expected:
        raise RuntimeError(f"batch {index} id mismatch: expected {expected}, received {ids}")
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index, reviews, "completed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--schema", default=str(ROOT / "schemas" / "codex_semantic_screen_v2.schema.json"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    source_rows = read_jsonl(Path(args.input).resolve())
    if args.limit:
        source_rows = source_rows[: args.limit]
    batches = _chunks(source_rows, args.batch_size)
    output = Path(args.output).resolve()
    schema = Path(args.schema).resolve()
    results: dict[int, list[dict[str, Any]]] = {}
    states: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(_run_batch, index, batch, output, schema, args.model, args.effort): index
            for index, batch in enumerate(batches, 1)
        }
        for future in as_completed(futures):
            index, reviews, state = future.result()
            results[index] = reviews
            states[state] += 1
            print(f"batch {index}/{len(batches)} {state} ({len(reviews)} records)", flush=True)

    labels = [review for index in sorted(results) for review in results[index]]
    by_id = {str(row["candidate_id"]): row for row in source_rows}
    screened = []
    for review in labels:
        row = dict(by_id[str(review["candidate_id"])])
        row.pop("source_payload", None)
        row["codex_semantic_screen"] = {
            **review,
            "screening_mode": "logged_in_codex_cli",
            "model": args.model,
            "reasoning_effort": args.effort,
        }
        screened.append(row)
    write_jsonl(output / "semantic_labels.jsonl", labels)
    write_jsonl(output / "screened_candidates.jsonl", screened)
    write_jsonl(
        output / "review_queue.jsonl",
        [row for row in screened if row["codex_semantic_screen"]["decision"] == "promote_to_review"],
    )
    report = {
        "schema_version": "codex-semantic-screen-v2",
        "input_count": len(source_rows),
        "output_count": len(labels),
        "batch_count": len(batches),
        "batch_states": dict(states),
        "model": args.model,
        "reasoning_effort": args.effort,
        "uses_external_api_key": False,
        "decision_counts": dict(sorted(Counter(row["decision"] for row in labels).items())),
        "causal_origin_counts": dict(sorted(Counter(row["causal_origin"] for row in labels).items())),
        "family_counts": dict(sorted(Counter(row["semantic_family"] for row in labels).items())),
        "benchmark_review_queue_counts": dict(sorted(Counter(
            row["benchmark"] for row in screened
            if row["codex_semantic_screen"]["decision"] == "promote_to_review"
        ).items())),
    }
    write_json(output / "semantic_screen_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
