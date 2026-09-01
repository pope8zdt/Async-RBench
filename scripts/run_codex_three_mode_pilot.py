"""Run a fixed 10-case ReAct/linear/async pilot through the logged-in Codex account."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.authoritative_capsule import load_capsule, score_submission  # noqa: E402
from async_rbench.react_baseline import BlockingReActEnvironment, score_react_state  # noqa: E402
from async_rbench.shared_task_scoring import (  # noqa: E402
    score_capsule_task_outcome,
    score_react_task_outcome,
)
from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402
from scripts.run_capsule_model_pilot import (  # noqa: E402
    SYSTEM as CAPSULE_SYSTEM,
    _async_event_messages,
    _async_initial_messages,
    _extract_json,
    _linear_messages,
)


MODEL = "gpt-5.6-sol"
MODES = ("react", "linear", "async")
REACT_SCHEMA = ROOT / "scripts" / "schemas" / "react_action.schema.json"
SUBMISSION_SCHEMA = ROOT / "scripts" / "schemas" / "capsule_submission.schema.json"
REACT_SYSTEM = (
    "You are the sole benchmark participant in a text-only simulator. Do not inspect the real "
    "filesystem and do not call Codex tools. The tools described in the task are simulated: return "
    "exactly one JSON action and the benchmark harness will synchronously return its observation. "
    "There are no subagents, background jobs, callbacks, or asynchronous interruptions."
)


@dataclass
class CodexTurn:
    thread_id: str
    message: str
    usage: dict[str, int]
    stdout: str
    stderr: str
    elapsed_sec: float


def _parse_codex_jsonl(stdout: str) -> tuple[str, str, dict[str, int]]:
    thread_id = ""
    messages: list[str] = []
    usage: dict[str, int] = {}
    for raw in stdout.splitlines():
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = str(event.get("thread_id") or "")
        elif event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                messages.append(str(item.get("text") or ""))
        elif event.get("type") == "turn.completed":
            usage = {key: int(value or 0) for key, value in (event.get("usage") or {}).items()}
    if not thread_id:
        raise RuntimeError("Codex output did not contain thread.started")
    if not messages:
        raise RuntimeError("Codex output did not contain an agent_message")
    return thread_id, messages[-1], usage


def _codex_command(
    prompt: str,
    *,
    thread_id: str | None,
    schema: Path | None,
    reasoning_effort: str,
) -> list[str]:
    if thread_id:
        command = [
            "codex", "exec", "resume", "--json", "--ignore-user-config", "--ignore-rules",
            "--model", MODEL, "--skip-git-repo-check",
            "-c", f'model_reasoning_effort="{reasoning_effort}"',
        ]
        if schema is not None:
            command.extend(["--output-schema", str(schema.resolve())])
        command.extend([thread_id, prompt])
        return command
    command = [
        "codex", "exec", "--json", "--ignore-user-config", "--ignore-rules",
        "--model", MODEL, "--sandbox", "read-only", "--skip-git-repo-check",
        "-c", f'model_reasoning_effort="{reasoning_effort}"',
    ]
    if schema is not None:
        command.extend(["--output-schema", str(schema.resolve())])
    command.append(prompt)
    return command


def _codex_turn(
    prompt: str,
    *,
    thread_id: str | None,
    schema: Path | None,
    reasoning_effort: str,
    timeout_sec: int,
    retries: int,
) -> CodexTurn:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        started = time.time()
        command = _codex_command(
            prompt,
            thread_id=thread_id,
            schema=schema,
            reasoning_effort=reasoning_effort,
        )
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Codex CLI exit {completed.returncode}: {completed.stderr[-1600:]}"
                )
            resolved_thread, message, usage = _parse_codex_jsonl(completed.stdout)
            if thread_id and resolved_thread != thread_id:
                raise RuntimeError(
                    f"resume thread mismatch: expected {thread_id}, got {resolved_thread}"
                )
            return CodexTurn(
                thread_id=resolved_thread,
                message=message,
                usage=usage,
                stdout=completed.stdout,
                stderr=completed.stderr,
                elapsed_sec=round(time.time() - started, 3),
            )
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise last_error or RuntimeError("Codex turn failed")


def _extract_action(text: str) -> tuple[str, dict[str, Any]]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    payload = json.loads(cleaned)
    action = payload.get("action") or {}
    tool = str(action.get("tool") or "")
    arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    if not tool:
        raise ValueError("missing action.tool")
    return tool, arguments


def _turn_artifact(turn: CodexTurn) -> dict[str, Any]:
    return {
        "thread_id": turn.thread_id,
        "message": turn.message,
        "usage": turn.usage,
        "elapsed_sec": turn.elapsed_sec,
        "stdout": turn.stdout,
        "stderr": turn.stderr,
    }


def _zero_task_score(public: dict[str, Any], expected: dict[str, Any], reason: str) -> dict[str, Any]:
    required_count = max(1, len(expected.get("affected_work_ids") or []))
    return {
        "case_id": public["case_id"],
        "score": 0.0,
        "test_point_count": required_count + 4,
        "passed_point_count": 0,
        "unscored_point_count": 0,
        "test_points": [],
        "zero_reason": reason,
    }


async def _run_react(
    case_dir: Path,
    output: Path,
    semaphore: asyncio.Semaphore,
    args: argparse.Namespace,
) -> dict[str, Any]:
    started = time.time()
    public, expected = load_capsule(case_dir)
    environment = BlockingReActEnvironment(public, expected)
    turns: list[CodexTurn] = []
    parse_errors: list[str] = []
    status = "scored"
    error: str | None = None
    async with semaphore:
        try:
            prompt = REACT_SYSTEM + "\n\n" + json.dumps(
                environment.start_payload(), ensure_ascii=False
            )
            turn = await asyncio.to_thread(
                _codex_turn,
                prompt,
                thread_id=None,
                schema=REACT_SCHEMA,
                reasoning_effort=args.reasoning_effort,
                timeout_sec=args.timeout_sec,
                retries=args.retries,
            )
            turns.append(turn)
            for _ in range(args.max_react_steps):
                try:
                    tool, arguments = _extract_action(turn.message)
                except Exception as exc:
                    parse_errors.append(str(exc))
                    correction = json.dumps({
                        "error": str(exc),
                        "instruction": "Return exactly one valid action JSON object now.",
                    }, ensure_ascii=False)
                    turn = await asyncio.to_thread(
                        _codex_turn,
                        correction,
                        thread_id=turn.thread_id,
                        schema=REACT_SCHEMA,
                        reasoning_effort=args.reasoning_effort,
                        timeout_sec=args.timeout_sec,
                        retries=args.retries,
                    )
                    turns.append(turn)
                    continue
                observation = environment.call(tool, arguments)
                if environment.state.finished:
                    break
                followup = json.dumps({
                    "simulated_tool_observation": observation,
                    "instruction": "The blocking call returned. Choose exactly one next JSON action.",
                }, ensure_ascii=False)
                turn = await asyncio.to_thread(
                    _codex_turn,
                    followup,
                    thread_id=turn.thread_id,
                    schema=REACT_SCHEMA,
                    reasoning_effort=args.reasoning_effort,
                    timeout_sec=args.timeout_sec,
                    retries=args.retries,
                )
                turns.append(turn)
            if not environment.state.finished:
                status = "scored_incomplete"
                error = f"react_step_limit:{args.max_react_steps}"
            task_score = score_react_task_outcome(public, expected, environment.state)
            diagnostic = score_react_state(public, expected, environment.state)
        except Exception as exc:
            status = "infra_failed"
            error = str(exc)
            task_score = None
            diagnostic = None
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "simulator_trace.jsonl", environment.trace)
    (output / "turns.json").write_text(
        json.dumps([_turn_artifact(item) for item in turns], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "state.json").write_text(
        json.dumps(environment.state.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if task_score is not None:
        (output / "task_score.json").write_text(
            json.dumps(task_score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if diagnostic is not None:
        (output / "process_diagnostic.json").write_text(
            json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return _episode_record(
        public, "react", status, task_score, diagnostic, turns, started, error,
        extra={"tool_step_count": len(environment.trace), "parse_error_count": len(parse_errors)},
    )


def _capsule_prompt(messages: list[dict[str, Any]]) -> str:
    return (
        "You are running inside a text-only benchmark simulator. Do not inspect the real filesystem "
        "or call Codex tools. Follow the benchmark payload and return only the requested JSON.\n\n"
        + "\n\n".join(
            f"{str(message['role']).upper()}: {message['content']}" for message in messages
        )
    )


async def _run_capsule(
    mode: str,
    case_dir: Path,
    output: Path,
    semaphore: asyncio.Semaphore,
    args: argparse.Namespace,
) -> dict[str, Any]:
    started = time.time()
    public, expected = load_capsule(case_dir)
    turns: list[CodexTurn] = []
    submission: dict[str, Any] | None = None
    error: str | None = None
    async with semaphore:
        try:
            if mode == "linear":
                turn = await asyncio.to_thread(
                    _codex_turn,
                    _capsule_prompt(_linear_messages(case_dir)),
                    thread_id=None,
                    schema=SUBMISSION_SCHEMA,
                    reasoning_effort=args.reasoning_effort,
                    timeout_sec=args.timeout_sec,
                    retries=args.retries,
                )
                turns.append(turn)
            else:
                initial = _async_initial_messages(case_dir)
                turn = await asyncio.to_thread(
                    _codex_turn,
                    _capsule_prompt(initial),
                    thread_id=None,
                    schema=None,
                    reasoning_effort=args.reasoning_effort,
                    timeout_sec=args.timeout_sec,
                    retries=args.retries,
                )
                turns.append(turn)
                events = _async_event_messages(case_dir)
                for index, event in enumerate(events, 1):
                    turn = await asyncio.to_thread(
                        _codex_turn,
                        str(event["content"]),
                        thread_id=turn.thread_id,
                        schema=SUBMISSION_SCHEMA if index == len(events) else None,
                        reasoning_effort=args.reasoning_effort,
                        timeout_sec=args.timeout_sec,
                        retries=args.retries,
                    )
                    turns.append(turn)
            try:
                submission = _extract_json(turn.message)
                task_score = score_capsule_task_outcome(public, expected, submission)
                diagnostic = score_submission(case_dir, submission, mode)
                status = "scored"
            except Exception as exc:
                error = f"model_protocol_failure:{exc}"
                status = "scored_protocol_failure"
                task_score = _zero_task_score(public, expected, error)
                diagnostic = None
        except Exception as exc:
            status = "infra_failed"
            error = str(exc)
            task_score = None
            diagnostic = None
    output.mkdir(parents=True, exist_ok=True)
    (output / "turns.json").write_text(
        json.dumps([_turn_artifact(item) for item in turns], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if submission is not None:
        (output / "submission.json").write_text(
            json.dumps(submission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if task_score is not None:
        (output / "task_score.json").write_text(
            json.dumps(task_score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if diagnostic is not None:
        (output / "process_diagnostic.json").write_text(
            json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return _episode_record(public, mode, status, task_score, diagnostic, turns, started, error)


def _episode_record(
    public: dict[str, Any],
    mode: str,
    status: str,
    task_score: dict[str, Any] | None,
    diagnostic: dict[str, Any] | None,
    turns: list[CodexTurn],
    started: float,
    error: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    usage: defaultdict[str, int] = defaultdict(int)
    for turn in turns:
        for key, value in turn.usage.items():
            usage[key] += int(value or 0)
    record = {
        "case_id": public["case_id"],
        "benchmark": public["source"].get("benchmark"),
        "model_requested": MODEL,
        "provider_auth": "Codex CLI logged in using ChatGPT",
        "mode": mode,
        "status": status,
        "task_score": task_score["score"] if task_score else None,
        "task_test_point_count": task_score["test_point_count"] if task_score else None,
        "task_passed_point_count": task_score["passed_point_count"] if task_score else None,
        "task_unscored_point_count": task_score["unscored_point_count"] if task_score else None,
        "process_diagnostic_score": diagnostic.get("score") if diagnostic else None,
        "request_count": len(turns),
        "thread_id": turns[0].thread_id if turns else "",
        "elapsed_sec": round(time.time() - started, 3),
        "usage": dict(usage),
        "error": error,
        **(extra or {}),
    }
    return record


def _stratified_sample(manifest: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in manifest:
        groups[str(row.get("benchmark"))].append(row)
    if {"OSWorld", "SWE-bench", "MultiAgentBench"}.issubset(groups):
        quotas = {"OSWorld": 3, "SWE-bench": 3, "MultiAgentBench": 4}
    else:
        quotas = {"GAIA2": 7, "SentinelBench": 2, "Terminal-Bench": 1}
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for benchmark, count in quotas.items():
        if len(groups[benchmark]) < count:
            raise ValueError(f"not enough {benchmark} cases for quota {count}")
        selected.extend(rng.sample(groups[benchmark], count))
    return sorted(selected, key=lambda row: str(row["case_id"]))


def _report(records: list[dict[str, Any]], sample: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    aggregates: dict[str, Any] = {}
    for mode in MODES:
        rows = [row for row in records if row["mode"] == mode]
        scored = [row for row in rows if row["task_score"] is not None]
        values = [float(row["task_score"]) for row in scored]
        diagnostic_values = [
            float(row["process_diagnostic_score"])
            for row in rows
            if row["process_diagnostic_score"] is not None
        ]
        aggregates[mode] = {
            "attempted_count": len(rows),
            "scored_count": len(scored),
            "coverage": round(len(scored) / len(rows), 6) if rows else 0.0,
            "main_macro_mean": round(sum(values) / len(values), 6) if values else None,
            "strict_task_pass_rate": round(
                sum(value >= 1.0 - 1e-9 for value in values) / len(values), 6
            ) if values else None,
            "mean_task_test_point_count": round(
                sum(int(row["task_test_point_count"]) for row in scored) / len(scored), 3
            ) if scored else None,
            "process_diagnostic_mean": round(
                sum(diagnostic_values) / len(diagnostic_values), 6
            ) if diagnostic_values else None,
            "infra_failed_count": sum(row["status"] == "infra_failed" for row in rows),
        }
    by_case: dict[str, dict[str, Any]] = {}
    for case_id in sorted({str(row["case_id"]) for row in records}):
        case_rows = [row for row in records if row["case_id"] == case_id]
        by_mode = {str(row["mode"]): row for row in case_rows}
        by_case[case_id] = {
            "benchmark": case_rows[0]["benchmark"],
            "task_test_point_count": next(
                (row["task_test_point_count"] for row in case_rows if row["task_test_point_count"] is not None),
                None,
            ),
            **{mode: (by_mode.get(mode) or {}).get("task_score") for mode in MODES},
            "async_minus_react": (
                round(float(by_mode["async"]["task_score"]) - float(by_mode["react"]["task_score"]), 6)
                if by_mode.get("async", {}).get("task_score") is not None
                and by_mode.get("react", {}).get("task_score") is not None else None
            ),
            "async_minus_linear": (
                round(float(by_mode["async"]["task_score"]) - float(by_mode["linear"]["task_score"]), 6)
                if by_mode.get("async", {}).get("task_score") is not None
                and by_mode.get("linear", {}).get("task_score") is not None else None
            ),
        }
    source_counts = Counter(str(row["benchmark"]) for row in sample["cases"])
    return {
        "schema_version": "codex-three-mode-pilot-1",
        "model": {
            "requested": MODEL,
            "reasoning_effort": args.reasoning_effort,
            "auth": "Codex CLI logged in using ChatGPT",
            "api_key_file_used": False,
        },
        "sample": {
            "seed": sample["seed"],
            "size": len(sample["cases"]),
            "selection": "fixed-seed stratified by benchmark; exact quotas recorded in source_counts",
            "source_counts": dict(sorted(source_counts.items())),
        },
        "scoring_policy": {
            "main_score": "macro mean of the same mode-neutral task outcome score over cases",
            "per_task_points": "one point per required action plus four invariant safety/closure points",
            "required_action_weight_mass": 0.70,
            "invariant_weights": {
                "no_superseded_action": 0.10,
                "no_extraneous_or_duplicate_action": 0.10,
                "prior_work_preserved": 0.05,
                "closure_verified": 0.05,
            },
            "async_process_points": "reported separately; never folded into the main score",
            "infrastructure_failures": "excluded from mean and exposed through coverage; valid model protocol failures score zero",
        },
        "episode_count": len(records),
        "status_counts": dict(sorted(Counter(str(row["status"]) for row in records).items())),
        "aggregates": aggregates,
        "by_case": by_case,
        "all_modes_full_coverage": all(value["coverage"] == 1.0 for value in aggregates.values()),
    }


async def _run(args: argparse.Namespace) -> int:
    production = Path(args.production).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = _stratified_sample(read_jsonl(production / "case_manifest.jsonl"), args.seed)
    sample = {"seed": args.seed, "cases": selected}
    (output / "sample_manifest.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    config = {
        "model": MODEL,
        "reasoning_effort": args.reasoning_effort,
        "auth": "Codex CLI logged in using ChatGPT",
        "command_safety": "read-only sandbox; user config and rules ignored; no API key file",
    }
    (output / "run_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    semaphore = asyncio.Semaphore(args.concurrency)
    jobs = []
    preserved: list[dict[str, Any]] = []
    for row in selected:
        case_dir = production / str(row["path"])
        for mode in MODES:
            episode_dir = output / "episodes" / str(row["case_id"]) / mode
            episode_path = episode_dir / "episode.json"
            if args.resume and episode_path.is_file():
                existing = json.loads(episode_path.read_text(encoding="utf-8"))
                if existing.get("status") != "infra_failed":
                    preserved.append(existing)
                    continue
            if mode == "react":
                jobs.append(_run_react(case_dir, episode_dir, semaphore, args))
            else:
                jobs.append(_run_capsule(mode, case_dir, episode_dir, semaphore, args))
    generated = list(await asyncio.gather(*jobs))
    for record in generated:
        episode_path = output / "episodes" / str(record["case_id"]) / str(record["mode"]) / "episode.json"
        episode_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            key: record[key]
            for key in ("case_id", "mode", "status", "task_score", "process_diagnostic_score", "elapsed_sec")
        }, ensure_ascii=False), flush=True)
    records = preserved + generated
    records.sort(key=lambda row: (str(row["case_id"]), MODES.index(str(row["mode"]))))
    write_jsonl(output / "episodes.jsonl", records)
    report = _report(records, sample, args)
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["all_modes_full_coverage"] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--production",
        default="artifacts/authoritative-case-300/04-case-production",
    )
    parser.add_argument(
        "--output",
        default="artifacts/authoritative-case-300/08-codex-5.6-sol-three-mode-10",
    )
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--max-react-steps", type=int, default=16)
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
