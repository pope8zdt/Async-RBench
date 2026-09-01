"""Run four source-native SWE cases in ReAct, linear, and async modes."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "native-model-pilot-v1"
MODELS = ("gpt-5.6-sol", "gpt-5.6-luna", "deepseek-v4-flash", "qwen3-coder-480b-a35b-instruct")
MODES = ("react", "linear", "async")
CASES = (
    "swe-late-constraint-3950516755",
    "swe-dependency-unblock-3361c7af50",
    "swe-dependency-unblock-8902c7f431",
    "swe-late-constraint-7ce47cda27",
)
MODEL_ALIASES = {"gpt-5.6-sol": "sol", "gpt-5.6-luna": "luna", "deepseek-v4-flash": "ds", "qwen3-coder-480b-a35b-instruct": "qwen"}
MODE_ALIASES = {"react": "r", "linear": "l", "async": "a"}
CASE_ALIASES = {case_id: f"c{index}" for index, case_id in enumerate(CASES)}


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 900, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    if check and result.returncode:
        raise RuntimeError(f"command failed {result.returncode}: {' '.join(command)}\n{result.stderr[-3000:]}")
    return result


def load_inputs() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    source_root = ROOT / "artifacts" / "source-native-v4"
    manifest = {row["case_id"]: row for row in (json.loads(line) for line in (source_root / "native_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line)}
    registry = {row["case_id"]: row for row in (json.loads(line) for line in (ROOT / "artifacts/native-runtime-v4/runtime_registry.jsonl").read_text(encoding="utf-8").splitlines() if line)}
    specs = {}
    for case_id in CASES:
        row = manifest[case_id]
        if registry.get(case_id, {}).get("status") != "gold_and_checkpoint_validated":
            raise RuntimeError(f"case is not runtime-qualified: {case_id}")
        specs[case_id] = json.loads((source_root / row["native_path"] / "native_case.json").read_text(encoding="utf-8"))
    return specs, registry


def credentials() -> dict[str, dict[str, str]]:
    lines = (ROOT / "APIKey.txt").read_text(encoding="utf-8-sig").splitlines()
    qwen = json.loads(lines[0][lines[0].index("{"):])
    return {
        "deepseek-v4-flash": {"key": lines[1].split("=", 1)[1].strip(), "base": "https://api.deepseek.com"},
        "qwen3-coder-480b-a35b-instruct": {"key": str(qwen["key"]), "base": str(qwen["url"]).rstrip("/") + "/v1"},
    }


def prepare_base(case_id: str, spec: dict[str, Any]) -> Path:
    base = ARTIFACT / "workspaces" / "base" / case_id
    if (base / ".git").is_dir():
        return base
    base_root = (ARTIFACT / "workspaces" / "base").resolve()
    if base.exists():
        resolved = base.resolve()
        if not resolved.is_relative_to(base_root):
            raise RuntimeError(f"refusing to replace base outside experiment root: {resolved}")
        shutil.rmtree(resolved)
    base.mkdir(parents=True, exist_ok=True)
    binding = spec["source_binding"]
    run(["git", "init"], cwd=base)
    run(["git", "remote", "add", "origin", f"https://github.com/{binding['repo']}.git"], cwd=base)
    run(["git", "fetch", "--depth", "1", "--filter=blob:none", "origin", str(binding["base_commit"])], cwd=base, timeout=900)
    run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=base, timeout=300)
    run(["git", "config", "core.autocrlf", "false"], cwd=base)
    run(["git", "config", "core.fileMode", "false"], cwd=base)
    return base


def create_worktree(base: Path, run_root: Path, model: str, mode: str, case_id: str) -> Path:
    workspace = run_root / "w" / MODEL_ALIASES[model] / MODE_ALIASES[mode] / CASE_ALIASES[case_id]
    workspace.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "worktree", "add", "--detach", str(workspace), "HEAD"], cwd=base, timeout=300)
    return workspace


def diff_bytes(workspace: Path) -> bytes:
    status = subprocess.run(["git", "status", "--porcelain=v1", "-z"], cwd=workspace, capture_output=True, check=False).stdout
    for record in (item for item in status.split(b"\0") if item.startswith(b"?? ")):
        path = record[3:].decode("utf-8", errors="surrogateescape")
        run(["git", "add", "-N", "--", path], cwd=workspace, check=False)
    result = subprocess.run(["git", "diff", "--binary", "HEAD"], cwd=workspace, capture_output=True, check=False)
    return result.stdout


def revision(workspace: Path) -> str:
    return hashlib.sha256(diff_bytes(workspace)).hexdigest()


def parse_codex(stdout: str) -> tuple[str, str, dict[str, int]]:
    thread, messages, usage = "", [], {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread = str(event.get("thread_id") or "")
        elif event.get("type") == "item.completed" and (event.get("item") or {}).get("type") == "agent_message":
            messages.append(str(event["item"].get("text") or ""))
        elif event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
    if not thread:
        raise RuntimeError("Codex did not return a thread id")
    return thread, messages[-1] if messages else "", usage


def codex_turn(model: str, workspace: Path, prompt: str, *, thread: str | None, creds: dict[str, dict[str, str]]) -> dict[str, Any]:
    environment = os.environ.copy()
    command = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]
    if thread:
        command += ["resume"]
    command += ["--json", "--ignore-user-config", "--ignore-rules", "--model", model, "--skip-git-repo-check"]
    if model == "deepseek-v4-flash":
        environment["DTBENCH_DS_KEY"] = creds[model]["key"]
        command += [
            "-c", 'model_provider="deepseek"',
            "-c", 'model_providers.deepseek.name="deepseek"',
            "-c", f'model_providers.deepseek.base_url="{creds[model]["base"]}"',
            "-c", 'model_providers.deepseek.env_key="DTBENCH_DS_KEY"',
            "-c", 'model_providers.deepseek.wire_api="responses"',
        ]
    command += ["-c", 'model_reasoning_effort="high"']
    if thread:
        command += [thread, prompt]
    else:
        command += ["-C", str(workspace), prompt]
    started = time.time()
    result = run(command, cwd=workspace, env=environment, timeout=1200)
    resolved_thread, message, usage = parse_codex(result.stdout)
    return {"thread": resolved_thread, "message": message, "usage": usage, "elapsed": round(time.time() - started, 3), "stdout": result.stdout[-20000:], "stderr": result.stderr[-4000:]}


def qwen_request(creds: dict[str, str], messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"model": "qwen3-coder-480b-a35b-instruct", "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0.1, "max_tokens": 8192}
    request = urllib.request.Request(creds["base"] + "/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + creds["key"]}, method="POST")
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode())


def qwen_tools(read_only: bool) -> list[dict[str, Any]]:
    definitions = [
        ("list_files", "List repository files", {"path": {"type": "string"}}, ["path"]),
        ("search", "Search repository text", {"query": {"type": "string"}, "path": {"type": "string"}}, ["query", "path"]),
        ("read_file", "Read a UTF-8 source file", {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path"]),
        ("git_diff", "Show current git diff", {}, []),
    ]
    if not read_only:
        definitions.append(("apply_patch", "Apply a unified git patch", {"patch": {"type": "string"}}, ["patch"]))
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": {"type": "object", "properties": p, "required": r, "additionalProperties": False}}} for n, d, p, r in definitions]


def safe_path(workspace: Path, raw: str) -> Path:
    target = (workspace / raw).resolve()
    if target != workspace.resolve() and not target.is_relative_to(workspace.resolve()):
        raise ValueError("path outside workspace")
    return target


def execute_qwen_tool(workspace: Path, name: str, args: dict[str, Any]) -> tuple[str, bool]:
    if name == "list_files":
        path = safe_path(workspace, str(args.get("path") or "."))
        result = run(["rg", "--files", str(path)], cwd=workspace, check=False)
        return result.stdout[-20000:], False
    if name == "search":
        path = safe_path(workspace, str(args.get("path") or "."))
        result = run(["rg", "-n", "-F", str(args.get("query") or ""), str(path)], cwd=workspace, check=False)
        return (result.stdout + result.stderr)[-20000:], False
    if name == "read_file":
        path = safe_path(workspace, str(args["path"]))
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start, end = max(1, int(args.get("start") or 1)), min(len(lines), int(args.get("end") or int(args.get("start") or 1) + 300))
        return "\n".join(f"{n}: {lines[n-1]}" for n in range(start, end + 1)), False
    if name == "git_diff":
        return diff_bytes(workspace).decode("utf-8", errors="replace")[-30000:], False
    if name == "apply_patch":
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", suffix=".patch", delete=False) as handle:
            handle.write(str(args.get("patch") or "")); patch_path = Path(handle.name)
        try:
            result = run(["git", "apply", "--whitespace=nowarn", str(patch_path)], cwd=workspace, check=False)
            return ("applied" if result.returncode == 0 else "failed: " + result.stderr[-4000:]), result.returncode == 0
        finally:
            patch_path.unlink(missing_ok=True)
    return "unknown tool", False


def qwen_turn(workspace: Path, prompt: str, *, state: list[dict[str, Any]] | None, creds: dict[str, str], read_only: bool, stop_after_first_write: bool = False) -> dict[str, Any]:
    messages = list(state or [{"role": "system", "content": "You are a coding agent. Work only in the supplied repository and use tools for evidence. Do not fabricate file contents."}])
    messages.append({"role": "user", "content": prompt})
    usage_total, applied = 0, False
    started = time.time()
    for _ in range(24):
        body = qwen_request(creds, messages, qwen_tools(read_only))
        usage_total += int((body.get("usage") or {}).get("total_tokens") or 0)
        message = dict(body["choices"][0]["message"])
        messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            return {"state": messages, "message": str(message.get("content") or ""), "usage": {"total_tokens": usage_total}, "elapsed": round(time.time() - started, 3)}
        for call in calls:
            function = call.get("function") or {}
            try: args = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError: args = {}
            output, wrote = execute_qwen_tool(workspace, str(function.get("name") or ""), args)
            messages.append({"role": "tool", "tool_call_id": str(call.get("id") or "call"), "content": output})
            applied = applied or wrote
        if applied and stop_after_first_write:
            return {"state": messages, "message": "CHECKPOINT_READY", "usage": {"total_tokens": usage_total}, "elapsed": round(time.time() - started, 3)}
    return {"state": messages, "message": "STEP_LIMIT", "usage": {"total_tokens": usage_total}, "elapsed": round(time.time() - started, 3)}


def agent_turn(model: str, workspace: Path, prompt: str, *, state: Any, creds: dict[str, dict[str, str]], read_only: bool = False, stop_after_first_write: bool = False) -> dict[str, Any]:
    if model.startswith("qwen"):
        return qwen_turn(workspace, prompt, state=state, creds=creds[model], read_only=read_only, stop_after_first_write=stop_after_first_write)
    result = codex_turn(model, workspace, prompt, thread=state, creds=creds)
    result["state"] = result["thread"]
    return result


def task_prompt(spec: dict[str, Any]) -> str:
    participant = json.loads((ROOT / "artifacts/source-native-v4" / "cases" / "swe_bench" / spec["case_id"] / "participant_task.json").read_text(encoding="utf-8"))
    return str(participant["problem_statement"])


def run_episode(model: str, mode: str, case_id: str, spec: dict[str, Any], base: Path, workspace: Path, creds: dict[str, dict[str, str]]) -> dict[str, Any]:
    problem = task_prompt(spec)
    common = f"Solve this repository issue. Make the minimal correct code change in the working tree. Do not alter tests.\n\nISSUE:\n{problem}"
    trace, checkpoint = [], None
    started = time.time()
    try:
        if mode == "react":
            turn = agent_turn(model, workspace, "You are the only agent; there are no subagents or asynchronous callbacks.\n" + common, state=None, creds=creds)
            trace.append({"role": "main", **{k: v for k, v in turn.items() if k != "state"}})
        elif mode == "linear":
            sub = agent_turn(model, base, "Act as a read-only specialist. Inspect the repository and diagnose this issue; return concrete file/function guidance, but make no edits.\n" + common, state=None, creds=creds, read_only=True)
            trace.append({"role": "subagent", **{k: v for k, v in sub.items() if k != "state"}})
            turn = agent_turn(model, workspace, common + "\n\nSPECIALIST RESULT AVAILABLE BEFORE WORK:\n" + sub["message"], state=None, creds=creds)
            trace.append({"role": "main", **{k: v for k, v in turn.items() if k != "state"}})
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                sub_future = pool.submit(agent_turn, model, base, "Act as a read-only specialist. Inspect the repository and diagnose this issue; return concrete file/function guidance, but make no edits.\n" + common, state=None, creds=creds, read_only=True)
                initial_future = pool.submit(agent_turn, model, workspace, "A specialist is running concurrently. Begin solving now. Make a concrete initial code change, then stop so the harness can deliver the callback.\n" + common, state=None, creds=creds, stop_after_first_write=True)
                initial = initial_future.result()
                checkpoint = revision(workspace)
                sub = sub_future.result()
            trace.append({"role": "main_pre_event", **{k: v for k, v in initial.items() if k != "state"}})
            trace.append({"role": "subagent", **{k: v for k, v in sub.items() if k != "state"}})
            if not diff_bytes(workspace):
                raise RuntimeError("async_checkpoint_unchanged")
            final = agent_turn(model, workspace, "ASYNC SPECIALIST CALLBACK (arrived after your persisted checkpoint):\n" + sub["message"] + "\nReassess your existing change, repair or complete it, and finish the issue.", state=initial["state"], creds=creds)
            trace.append({"role": "main_post_event", **{k: v for k, v in final.items() if k != "state"}})
        patch = diff_bytes(workspace).decode("utf-8", errors="replace")
        status = "produced" if patch.strip() else "invalid_empty_patch"
        error = None
    except Exception as exc:
        patch, status, error = diff_bytes(workspace).decode("utf-8", errors="replace"), "invalid_episode", f"{type(exc).__name__}:{exc}"
    return {"case_id": case_id, "instance_id": spec["source_binding"]["instance_id"], "model": model, "mode": mode, "status": status, "error": error, "checkpoint_revision": checkpoint, "final_revision": revision(workspace), "patch": patch, "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(), "trace": trace, "elapsed": round(time.time() - started, 3)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default=",".join(MODELS))
    args = parser.parse_args()
    selected_models = tuple(item.strip() for item in args.models.split(",") if item.strip())
    unknown = set(selected_models) - set(MODELS)
    if unknown:
        raise SystemExit(f"unknown models: {sorted(unknown)}")
    specs, registry = load_inputs(); creds = credentials()
    run_id = "run-" + time.strftime("%Y%m%d-%H%M%S")
    run_root = ARTIFACT / run_id; run_root.mkdir(parents=True)
    (run_root / "selection.json").write_text(json.dumps({"seed": 20260830, "cases": list(CASES), "models": list(selected_models), "modes": list(MODES)}, indent=2) + "\n", encoding="utf-8")
    bases = {case_id: prepare_base(case_id, specs[case_id]) for case_id in CASES}
    results = []
    for model in selected_models:
        for case_id in CASES:
            for mode in MODES:
                workspace = create_worktree(bases[case_id], run_root, model, mode, case_id)
                result = run_episode(model, mode, case_id, specs[case_id], bases[case_id], workspace, creds)
                episode = run_root / "episodes" / model / mode / f"{case_id}.json"; episode.parent.mkdir(parents=True, exist_ok=True)
                episode.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                results.append({k: v for k, v in result.items() if k not in {"trace", "patch"}})
                print(json.dumps(results[-1], ensure_ascii=True), flush=True)
    (run_root / "generation_manifest.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in results), encoding="utf-8")
    print(str(run_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
