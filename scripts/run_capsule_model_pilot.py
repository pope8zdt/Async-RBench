"""Run a fixed-seed five-case linear/async pilot against two API models."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.authoritative_capsule import canonical_sha256, load_capsule, score_submission  # noqa: E402
from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402


def _credentials(path: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.startswith("2.deepseek-v4-flash="):
            result["deepseek-v4-flash"] = {
                "key": line.split("=", 1)[1].strip(),
                "url": "https://api.deepseek.com/chat/completions",
            }
        elif line.startswith("3.gpt-5.4-2026-03-05") and "{" in line:
            payload = json.loads(line[line.index("{"):])
            base = str(payload["url"]).rstrip("/")
            result["gpt-5.4-2026-03-05"] = {
                "key": str(payload["key"]),
                "url": base + "/v1/chat/completions",
            }
    required = {"gpt-5.4-2026-03-05", "deepseek-v4-flash"}
    if set(result) != required:
        raise RuntimeError(f"credential file does not provide expected model entries: {sorted(required - set(result))}")
    return result


def _request(config: dict[str, str], model: str, messages: list[dict]) -> dict:
    payload: dict[str, Any] = {"model": model, "messages": messages}
    if model.startswith("gpt-"):
        payload.update({"max_completion_tokens": 16384, "reasoning_effort": "high"})
    else:
        # V4 thinking defaults to high and can consume the entire completion
        # budget before emitting JSON on this constrained protocol task.  The
        # official API exposes an explicit non-thinking mode for this case.
        payload.update({"max_tokens": 8192, "thinking": {"type": "disabled"}})
    payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        config["url"], data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config['key']}"},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-1600:]
            last_error = RuntimeError(f"HTTP {exc.code}: {detail}")
            if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = RuntimeError(f"request failed: {exc}")
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise last_error or RuntimeError("model request failed")


def _message(response: dict) -> dict:
    return dict(response["choices"][0]["message"])


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    decoder = json.JSONDecoder()
    candidates = []
    for match in re.finditer(r"\{", cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    for value in reversed(candidates):
        if "case_id" in value and "source_id" in value:
            return value
    raise ValueError("response did not contain a submission JSON object")


def _submission_contract(public: dict, expected: dict, mode: str) -> dict:
    closure_payload = {
        "event_id": expected["event_id"],
        "final_action_ids": list(expected["affected_work_ids"]),
        "preserved_work_ids": list(expected["prior_work_ids"]),
    }
    return {
        "case_id": public["case_id"],
        "source_id": public["source"]["source_id"],
        "instruction_sha256": public["source"]["instruction_sha256"],
        "event_release_tick": public["scenarios"][mode]["event_release_tick"],
        "closure_revision_after_reverification": canonical_sha256(closure_payload),
        "privacy_note": (
            "The correct required, superseded, and preserved ID sets are intentionally not "
            "provided. Infer them from the task, candidate catalogue, completed work, and event."
        ),
        "required_json_shape": {
            "case_id": "string", "source_id": "string", "instruction_sha256": "string",
            "initial_plan": {"completed_before_event": ["id"], "provisional_action_ids": ["id"]},
            "event_intake": {"event_id": "string", "sequence": "integer", "accepted": "boolean"},
            "revised_plan": {
                "preserved_work_ids": ["id"], "invalidated_work_ids": ["id"],
                "required_action_ids": ["id"],
            },
            "final_action_ids": ["id"],
            "closure": {"reverified": "boolean", "final_revision": "string"},
        },
    }


def _participant_view(public: dict) -> dict:
    causal = public["causal_record"]
    candidates = []
    for item in list(causal.get("affected_work") or []) + list(causal.get("superseded_work") or []):
        candidates.append({
            "action_id": item["id"],
            "description": item.get("description"),
        })
    candidates.sort(key=lambda item: canonical_sha256({
        "case_id": public["case_id"], "action_id": item["action_id"],
    }))
    return {
        "original_task": public["source"]["instruction"],
        "already_completed_work": public["causal_record"]["prior_work"],
        "candidate_action_catalogue": candidates,
    }


SYSTEM = (
    "You are a benchmark participant. Follow the provided source record and event lifecycle exactly. "
    "Return the requested JSON object only, without markdown or commentary. Preserve unaffected completed work, "
    "reject superseded provisional work, integrate the authoritative event, and reverify closure."
)


def _linear_messages(case_dir: Path) -> list[dict]:
    public, expected = load_capsule(case_dir)
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps({
            "mode": "linear", "task": _participant_view(public),
            "event_status": "authoritative_final_result_already_available",
            "event_sequence": public["causal_record"].get("event_sequence") or [
                public["causal_record"]["independent_event"]
            ],
            "submission_contract": _submission_contract(public, expected, "linear"),
        }, ensure_ascii=False)},
    ]


def _async_initial_messages(case_dir: Path) -> list[dict]:
    public, expected = load_capsule(case_dir)
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps({
            "mode": "async_pre_event", "task": _participant_view(public),
            "source_identity": {
                "case_id": public["case_id"], "source_id": public["source"]["source_id"],
                "instruction_sha256": public["source"]["instruction_sha256"],
            },
            "instruction": (
                "Begin the task now using only information currently available. Return a compact "
                "pre-event checkpoint JSON containing completed work and any provisional choices; "
                "the independent event is not available yet."
            ),
        }, ensure_ascii=False)},
    ]


def _async_event_messages(case_dir: Path) -> list[dict]:
    public, expected = load_capsule(case_dir)
    events = public["causal_record"].get("event_sequence") or [
        public["causal_record"]["independent_event"]
    ]
    messages = []
    for index, event in enumerate(events, 1):
        final = index == len(events)
        messages.append({"role": "user", "content": json.dumps({
            "type": "asynchronous_result_delivery",
            "sequence_index": index,
            "is_final_authoritative_result": final,
            "interrupts_previous_work": True,
            "independent_event": event,
            "submission_contract": _submission_contract(public, expected, "async") if final else None,
            "instruction": (
                "This is a provisional, unverified subagent result. Continue the task and return "
                "an updated checkpoint; a verifier may still correct it."
                if not final else
                "This authoritative verifier result supersedes any conflicting provisional result. "
                "Selectively roll back stale work, preserve valid work, and return the final submission JSON only."
            ),
        }, ensure_ascii=False)})
    return messages


async def _episode(
    semaphore: asyncio.Semaphore, config: dict[str, str], model: str, mode: str,
    case_dir: Path, output: Path,
) -> dict:
    started = time.time()
    output.mkdir(parents=True, exist_ok=True)
    response = None
    pre_event_response = None
    submission = None
    score = None
    try:
        async with semaphore:
            if mode == "linear":
                messages = _linear_messages(case_dir)
                response = await asyncio.to_thread(_request, config, model, messages)
                pre_event_response = None
            else:
                messages = _async_initial_messages(case_dir)
                pre_event_response = await asyncio.to_thread(_request, config, model, messages)
                messages.append(_message(pre_event_response))
                event_messages = _async_event_messages(case_dir)
                for event_index, event_message in enumerate(event_messages, 1):
                    messages.append(event_message)
                    response = await asyncio.to_thread(_request, config, model, messages)
                    if event_index < len(event_messages):
                        messages.append(_message(response))
        assistant = _message(response)
        answer_text = "\n".join(
            str(assistant.get(field) or "") for field in ("reasoning_content", "content")
        )
        submission = _extract_json(answer_text)
        score = score_submission(case_dir, submission, mode)
        status = "scored"
        error = None
    except Exception as exc:  # preserve every failed episode for audit
        status = "failed"
        error = str(exc)
    record = {
        "case_id": case_dir.name, "model": model, "mode": mode, "status": status,
        "score": score["score"] if score else None,
        "unscored_point_count": score["unscored_point_count"] if score else 8,
        "elapsed_sec": round(time.time() - started, 3), "error": error,
        "resolved_model": str((response or {}).get("model") or ""),
        "usage": (response or {}).get("usage") or {},
    }
    (output / "episode.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if pre_event_response is not None:
        (output / "pre_event_response.json").write_text(json.dumps(pre_event_response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if response is not None:
        (output / "final_response.json").write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if submission is not None:
        (output / "submission.json").write_text(json.dumps(submission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if score is not None:
        (output / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in ("case_id", "model", "mode", "status", "score", "elapsed_sec", "error")}, ensure_ascii=False), flush=True)
    return record


async def _run(args: argparse.Namespace) -> int:
    production = Path(args.production).resolve()
    manifest = read_jsonl(production / "case_manifest.jsonl")
    rng = random.Random(args.seed)
    selected = rng.sample(manifest, args.count)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sample = {
        "seed": args.seed, "population_size": len(manifest), "sample_size": len(selected),
        "cases": selected,
    }
    (output / "sample_manifest.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    credentials = _credentials(Path(args.key_file).resolve())
    models = ["gpt-5.4-2026-03-05", "deepseek-v4-flash"]
    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = []
    preserved = []
    for row in selected:
        case_dir = production / str(row["path"])
        for model in models:
            for mode in ("linear", "async"):
                episode_dir = output / "episodes" / model / row["case_id"] / mode
                existing_path = episode_dir / "episode.json"
                if args.resume and existing_path.is_file():
                    existing = json.loads(existing_path.read_text(encoding="utf-8"))
                    if existing.get("status") == "scored":
                        preserved.append(existing)
                        continue
                tasks.append(_episode(semaphore, credentials[model], model, mode, case_dir, episode_dir))
    records = preserved + list(await asyncio.gather(*tasks))
    records.sort(key=lambda row: (row["model"], row["case_id"], row["mode"]))
    write_jsonl(output / "episodes.jsonl", records)
    aggregates = {}
    for model in models:
        model_rows = [row for row in records if row["model"] == model]
        modes = {}
        for mode in ("linear", "async"):
            rows = [row for row in model_rows if row["mode"] == mode]
            scored = [float(row["score"]) for row in rows if row["status"] == "scored"]
            modes[mode] = {
                "episode_count": len(rows), "scored_count": len(scored),
                "mean_score": round(sum(scored) / len(scored), 6) if scored else None,
                "failed_count": sum(row["status"] != "scored" for row in rows),
            }
        aggregates[model] = {
            "modes": modes,
            "async_minus_linear": (
                round(modes["async"]["mean_score"] - modes["linear"]["mean_score"], 6)
                if modes["async"]["mean_score"] is not None and modes["linear"]["mean_score"] is not None
                else None
            ),
        }
    report = {
        "schema_version": "capsule-model-pilot-1", "sample": sample,
        "episode_count": len(records),
        "status_counts": dict(sorted(Counter(row["status"] for row in records).items())),
        "aggregates": aggregates,
        "unscored_or_failed_count": sum(row["status"] != "scored" or row["unscored_point_count"] > 0 for row in records),
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if all(row["status"] == "scored" for row in records) else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--key-file", default="APIKey.txt")
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
