"""Run the fixed five-case sample through a blocking single-agent ReAct baseline."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.authoritative_capsule import load_capsule  # noqa: E402
from async_rbench.react_baseline import BlockingReActEnvironment, score_react_state  # noqa: E402
from async_rbench.trajectory_curation import write_jsonl  # noqa: E402
from scripts.run_capsule_model_pilot import _credentials, _message, _request  # noqa: E402


SYSTEM = (
    "You are the only agent solving the task. Use a standard blocking ReAct loop: choose one tool, "
    "wait for its observation, then choose the next tool. There are no subagents, background jobs, "
    "callbacks, or asynchronous interruptions. Return exactly one JSON object per turn using the "
    "declared action shape. Inspect authoritative evidence before dependent actions and inspect the "
    "final state before finishing."
)


def _start_prompt(environment: BlockingReActEnvironment) -> str:
    """Concise, provider-neutral rendering of the same public ReAct contract."""
    task = str(environment.public["source"]["instruction"])
    return (
        f"Task: {task}\n\n"
        "Available blocking tools: inspect_current_state; query_authoritative_evidence; "
        "execute_action(action_id); inspect_final_state; finish(summary). "
        "Reply with one JSON object shaped as "
        "{\"action\":{\"tool\":\"tool_name\",\"arguments\":{}}}. "
        "Choose exactly one tool now and wait for its observation."
    )


def _baseline_request(config: dict[str, str], model: str, messages: list[dict]) -> dict:
    """Use the same audited model profiles as the prior Async pilot."""
    return _request(config, model, messages)


def _extract_command(response: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    assistant = _message(response)
    content = str(assistant.get("content") or "").strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for match in re.finditer(r"\{", content):
        try:
            value, _ = decoder.raw_decode(content[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    for value in reversed(candidates):
        action = value.get("action") if isinstance(value.get("action"), dict) else value
        tool = action.get("tool") if isinstance(action, dict) else None
        if isinstance(tool, str) and tool:
            arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            return tool, arguments
    raise ValueError("response did not contain a ReAct tool action")


async def _episode(
    semaphore: asyncio.Semaphore,
    config: dict[str, str],
    model: str,
    case_dir: Path,
    output: Path,
    max_steps: int,
    outer_retries: int,
    retry_cooldown_sec: float,
    gpt_inter_request_delay_sec: float,
) -> dict[str, Any]:
    started = time.time()
    output.mkdir(parents=True, exist_ok=True)
    public, expected = load_capsule(case_dir)
    environment = BlockingReActEnvironment(public, expected)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _start_prompt(environment)},
    ]
    responses: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    error: str | None = None
    try:
        async with semaphore:
            for _ in range(max_steps):
                last_request_error: Exception | None = None
                response = None
                for outer_attempt in range(outer_retries + 1):
                    try:
                        response = await asyncio.to_thread(_baseline_request, config, model, messages)
                        break
                    except Exception as exc:
                        last_request_error = exc
                        retryable = "HTTP 429" in str(exc) or "HTTP 5" in str(exc)
                        if not retryable or outer_attempt >= outer_retries:
                            raise
                        await asyncio.sleep(retry_cooldown_sec * (outer_attempt + 1))
                if response is None:
                    raise last_request_error or RuntimeError("model request returned no response")
                responses.append(response)
                assistant = _message(response)
                messages.append({
                    "role": "assistant",
                    "content": str(assistant.get("content") or ""),
                })
                try:
                    tool, arguments = _extract_command(response)
                except ValueError as exc:
                    parse_errors.append(str(exc))
                    messages.append({
                        "role": "user",
                        "content": json.dumps({
                            "tool_observation": {"error": str(exc)},
                            "instruction": "Return one valid action JSON object.",
                        }, ensure_ascii=False),
                    })
                    if model.startswith("gpt-") and gpt_inter_request_delay_sec > 0:
                        await asyncio.sleep(gpt_inter_request_delay_sec)
                    continue
                observation = environment.call(tool, arguments)
                messages.append({
                    "role": "user",
                    "content": json.dumps({
                        "tool_observation": observation,
                        "instruction": (
                            "The blocking call has returned. Choose the next tool action."
                            if not environment.state.finished else "Episode finished."
                        ),
                    }, ensure_ascii=False),
                })
                if environment.state.finished:
                    break
                if model.startswith("gpt-") and gpt_inter_request_delay_sec > 0:
                    # Some relay credentials enforce a strict per-key request
                    # interval.  Pace only GPT turns; this is infrastructure
                    # handling and is excluded from task correctness scoring.
                    await asyncio.sleep(gpt_inter_request_delay_sec)
        score = score_react_state(public, expected, environment.state)
        if not environment.state.finished:
            error = f"step_limit_exceeded:{max_steps}"
            status = "incomplete"
        else:
            status = "scored"
    except Exception as exc:  # preserve failures for audit
        error = str(exc)
        score = None
        status = "failed"

    trace_path = output / "react_trace.jsonl"
    write_jsonl(trace_path, environment.trace)
    (output / "state.json").write_text(
        json.dumps(environment.state.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "responses.json").write_text(
        json.dumps(responses, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if score is not None:
        (output / "score.json").write_text(
            json.dumps(score, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    resolved = [str(item.get("model") or "") for item in responses if item.get("model")]
    usage = {
        "prompt_tokens": sum(int((item.get("usage") or {}).get("prompt_tokens") or 0) for item in responses),
        "completion_tokens": sum(int((item.get("usage") or {}).get("completion_tokens") or 0) for item in responses),
        "total_tokens": sum(int((item.get("usage") or {}).get("total_tokens") or 0) for item in responses),
        "request_count": len(responses),
    }
    record = {
        "case_id": public["case_id"],
        "benchmark": public["source"].get("benchmark"),
        "model": model,
        "resolved_model": resolved[-1] if resolved else "",
        "execution_mode": "react_linear",
        "status": status,
        "score": score["score"] if score else None,
        "test_point_count": score["test_point_count"] if score else None,
        "passed_point_count": score["passed_point_count"] if score else None,
        "unscored_point_count": score["unscored_point_count"] if score else None,
        "tool_step_count": len(environment.trace),
        "parse_error_count": len(parse_errors),
        "finished": environment.state.finished,
        "elapsed_sec": round(time.time() - started, 3),
        "usage": usage,
        "error": error,
    }
    (output / "episode.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return record


async def _run(args: argparse.Namespace) -> int:
    production = Path(args.production).resolve()
    old_sample_path = Path(args.sample_manifest).resolve()
    sample = json.loads(old_sample_path.read_text(encoding="utf-8"))
    selected = list(sample.get("cases") or [])
    if len(selected) != 5:
        raise ValueError(f"expected the prior five-case sample, got {len(selected)}")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "sample_manifest.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    credentials = _credentials(Path(args.key_file).resolve())
    models = [value.strip() for value in args.models.split(",") if value.strip()]
    allowed_models = {"gpt-5.4-2026-03-05", "deepseek-v4-flash"}
    if not models or not set(models) <= allowed_models:
        raise ValueError(f"models must be selected from {sorted(allowed_models)}")
    force_models = {value.strip() for value in args.force_models.split(",") if value.strip()}
    if not force_models <= set(models):
        raise ValueError("force-models must be a subset of models")
    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = []
    preserved: list[dict[str, Any]] = []
    for row in selected:
        case_dir = production / str(row["path"])
        for model in models:
            episode_dir = output / "episodes" / model / str(row["case_id"])
            episode_path = episode_dir / "episode.json"
            if args.resume and model not in force_models and episode_path.is_file():
                existing = json.loads(episode_path.read_text(encoding="utf-8"))
                if existing.get("status") == "scored":
                    preserved.append(existing)
                    continue
            tasks.append(_episode(
                semaphore, credentials[model], model, case_dir, episode_dir, args.max_steps,
                args.outer_retries, args.retry_cooldown_sec, args.gpt_inter_request_delay_sec,
            ))
    records = preserved + list(await asyncio.gather(*tasks))
    records.sort(key=lambda row: (row["model"], row["case_id"]))
    write_jsonl(output / "episodes.jsonl", records)
    aggregates: dict[str, Any] = {}
    for model in models:
        rows = [row for row in records if row["model"] == model]
        scored = [float(row["score"]) for row in rows if row["status"] == "scored"]
        aggregates[model] = {
            "episode_count": len(rows),
            "scored_count": len(scored),
            "mean_score": round(sum(scored) / len(scored), 6) if scored else None,
            "finished_count": sum(bool(row["finished"]) for row in rows),
            "failed_count": sum(row["status"] != "scored" for row in rows),
            "step_limit_count": sum(str(row.get("error") or "").startswith("step_limit") for row in rows),
        }
    report = {
        "schema_version": "react-baseline-pilot-1",
        "baseline_definition": (
            "single main agent; blocking tool observations; no subagents, concurrency, gateway, "
            "background work, or asynchronous interruption"
        ),
        "request_profiles": {
            "gpt-5.4-2026-03-05": {
                "reasoning_effort": "high", "max_completion_tokens": 16384,
                "response_format": "json_object",
            },
            "deepseek-v4-flash": {
                "thinking": "disabled", "max_tokens": 8192,
                "response_format": "json_object",
            },
        },
        "sample_source": str(old_sample_path),
        "sample_seed": sample.get("seed"),
        "sample_size": len(selected),
        "episode_count": len(records),
        "status_counts": dict(sorted(Counter(row["status"] for row in records).items())),
        "unscored_or_failed_count": sum(
            row["status"] != "scored" or int(row.get("unscored_point_count") or 0) > 0
            for row in records
        ),
        "aggregates": aggregates,
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["unscored_or_failed_count"] == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", required=True)
    parser.add_argument("--sample-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--key-file", default="APIKey.txt")
    parser.add_argument("--max-steps", type=int, default=16)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--models", default="gpt-5.4-2026-03-05,deepseek-v4-flash",
        help="Comma-separated subset of the two pilot models.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--force-models", default="",
        help="Comma-separated selected models to rerun even when --resume finds scored episodes.",
    )
    parser.add_argument("--outer-retries", type=int, default=0)
    parser.add_argument("--retry-cooldown-sec", type=float, default=30.0)
    parser.add_argument("--gpt-inter-request-delay-sec", type=float, default=0.0)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
