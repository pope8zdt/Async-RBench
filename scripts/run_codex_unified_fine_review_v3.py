"""Run independent Codex fixed-choice fine reviews over the unified inventory."""

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

from async_rbench.unified_case_v3 import read_jsonl  # noqa: E402


LENSES = {
    "causal": """You are the causal-methodology reviewer. Focus on whether the event is genuinely produced independently of the focal agent, arrives after useful work, and counterfactually changes only a task-supported downstream subset. Reject relabelled sequential command feedback or the focal model's own thought/action. A controlled injection is allowed only when the original task genuinely supports an independently delegable, task-specific payload.""",
    "engineering": """You are the benchmark-engineering reviewer. Focus on source fidelity, task-specific affected actions, mode-neutral outcome scoring, leakage, and source-native replay. A symbolic capsule may be keep_normalized only as a calibration blueprint when its causal record is concrete and faithful; source_native_replay_ready must still be no if the real OS/VM/repository/multi-agent environment is absent. Truncated instructions, generic response templates, categorical event labels, or missing provenance require rebuild or reject.""",
}

PROMPT = """__LENS__

Review every record independently for an academic Async-vs-Linear replanning benchmark.

Decision meanings:
- keep_normalized: the case is a concrete, source-faithful, causally valid blueprint and can remain in the unified runnable capsule pool after mechanical schema/scoring normalization. This does NOT mean formal benchmark promotion.
- rebuild: the underlying source task is valuable, but the current case needs new evidence, a task-specific event/affected plan, restored source text, or a source-native evaluator.
- reject: the task cannot support the claimed async boundary, the evidence is corrupted/invalid, or repair would amount to inventing a different task.

Do not overlook supplied deterministic issues, but verify them against the excerpts. The field
instruction_excerpt may be clipped solely for review transport; never call the stored source
truncated merely because review_excerpt_clipped=true. Only the explicit deterministic issue
truncated_instruction indicates that the stored source itself appears truncated. Do not treat an
oracle score as empirical model challenge evidence. Same outcome tests must be applicable to
ReAct, Linear, and Async. Return exactly one review per unified_candidate_id in the supplied order.
Keep each rationale under 100 words.

RECORDS:
__RECORDS__
"""


def clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def compact(row: dict[str, Any]) -> dict[str, Any]:
    event = row.get("independent_event") or {}
    instruction = " ".join(str(row.get("instruction") or "").split())
    return {
        "unified_candidate_id": row["unified_candidate_id"],
        "collection": row["collection"],
        "benchmark": row["benchmark"],
        "evidence_class": row["evidence_class"],
        "current_family": row["current_family"],
        "instruction_excerpt": instruction[:1000],
        "stored_instruction_length": len(instruction),
        "review_excerpt_clipped": len(instruction) > 1000,
        "prior_work": [clip(item.get("description"), 300) for item in (row.get("prior_work") or [])[:3]],
        "independent_event": {
            "kind": event.get("kind"),
            "producer": event.get("producer"),
            "authority": event.get("authority"),
            "description": clip(event.get("description"), 650),
        },
        "affected_work": [clip(item.get("description"), 420) for item in (row.get("affected_work") or [])[:7]],
        "superseded_work": [clip(item.get("description"), 300) for item in (row.get("superseded_work") or [])[:4]],
        "deterministic_issues": row.get("deterministic_issues") or [],
    }


def chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


def run_batch(
    index: int,
    batch: list[dict[str, Any]],
    output: Path,
    schema: Path,
    model: str,
    effort: str,
    reviewer: str,
) -> tuple[int, list[dict[str, Any]], str]:
    batch_dir = output / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    result_path = batch_dir / f"batch-{index:04d}.result.json"
    log_path = batch_dir / f"batch-{index:04d}.stderr.log"
    input_path = batch_dir / f"batch-{index:04d}.input.json"
    expected_ids = [str(row["unified_candidate_id"]) for row in batch]
    payload = [compact(row) for row in batch]
    input_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    if result_path.is_file():
        try:
            cached = json.loads(result_path.read_text(encoding="utf-8"))
            reviews = list(cached.get("reviews") or [])
            if [str(item.get("unified_candidate_id")) for item in reviews] == expected_ids:
                return index, reviews, "cached"
        except (OSError, json.JSONDecodeError):
            pass
    prompt = PROMPT.replace("__LENS__", LENSES[reviewer]).replace(
        "__RECORDS__", json.dumps(payload, ensure_ascii=True)
    )
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
        command, input=prompt, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=1200, check=False,
    )
    log_path.write_text(
        f"exit_code={completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        encoding="utf-8",
    )
    try:
        result = json.loads(last_message.read_text(encoding="utf-8"))
        reviews = list(result.get("reviews") or [])
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"batch {index} invalid result; see {log_path}: {exc}") from exc
    finally:
        last_message.unlink(missing_ok=True)
    received = [str(item.get("unified_candidate_id")) for item in reviews]
    if received != expected_ids:
        raise RuntimeError(f"batch {index} ID mismatch: expected {expected_ids}, received {received}")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index, reviews, "completed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="artifacts/unified-case-set-v3/00-inventory/fine_review_queue.jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviewer", choices=tuple(LENSES), required=True)
    parser.add_argument("--schema", default=str(ROOT / "schemas" / "codex_unified_fine_review_v3.schema.json"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    rows = read_jsonl(Path(args.input).resolve())
    if args.limit:
        rows = rows[:args.limit]
    grouped = chunks(rows, args.batch_size)
    output = Path(args.output).resolve()
    schema = Path(args.schema).resolve()
    results: dict[int, list[dict[str, Any]]] = {}
    states: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                run_batch, index, batch, output, schema, args.model, args.effort, args.reviewer
            ): index
            for index, batch in enumerate(grouped, 1)
        }
        for future in as_completed(futures):
            index, reviews, state = future.result()
            results[index] = reviews
            states[state] += 1
            print(f"{args.reviewer} batch {index}/{len(grouped)} {state} ({len(reviews)})", flush=True)
    labels = [review for index in sorted(results) for review in results[index]]
    output.mkdir(parents=True, exist_ok=True)
    (output / "reviews.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in labels),
        encoding="utf-8",
    )
    report = {
        "schema_version": "codex-unified-fine-review-v3",
        "reviewer": args.reviewer,
        "model": args.model,
        "reasoning_effort": args.effort,
        "uses_external_api_key": False,
        "input_count": len(rows),
        "output_count": len(labels),
        "batch_count": len(grouped),
        "batch_states": dict(states),
        "decision_counts": dict(sorted(Counter(row["decision"] for row in labels).items())),
        "primary_issue_counts": dict(sorted(Counter(row["primary_issue"] for row in labels).items())),
        "source_fidelity_counts": dict(sorted(Counter(row["source_fidelity"] for row in labels).items())),
        "source_native_replay_ready_counts": dict(sorted(Counter(row["source_native_replay_ready"] for row in labels).items())),
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
