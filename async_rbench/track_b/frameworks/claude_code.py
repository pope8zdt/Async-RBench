from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult
from .common import parse_protocol_result, render_protocol_prompt
from .codex_cli import protect_process, terminate_process


QueryFn = Callable[..., Awaitable[dict[str, Any]]]
_ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "LANG", "LC_ALL",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR",
}
_SYSTEM_PROMPT = (
    "You select benchmark actions using only the supplied public request. "
    "Return the requested JSON response; the benchmark executes the actions."
)


def _child_environment(config: TrackBConfig, directory: Path) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key.upper() in _ENV_ALLOWLIST}
    for name in ("home", "config", "tmp"):
        (directory / name).mkdir()
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
        environment[key] = str(directory / "home")
    for key in ("TMP", "TEMP", "TMPDIR"):
        environment[key] = str(directory / "tmp")
    environment["CLAUDE_CONFIG_DIR"] = str(directory / "config")
    environment["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    selected = config.credential_env or "ANTHROPIC_API_KEY"
    credential = os.environ.get(selected, "")
    if credential:
        destination = "CLAUDE_CODE_OAUTH_TOKEN" if selected == "CLAUDE_CODE_OAUTH_TOKEN" else "ANTHROPIC_API_KEY"
        environment[destination] = credential
    return environment


def _validate_options(config: TrackBConfig) -> None:
    if set(config.framework_options) - {"permission_mode"}:
        raise ValueError("unsupported Claude Code framework options")
    if config.framework_options.get("permission_mode", "dontAsk") != "dontAsk":
        raise ValueError("Claude Code benchmark requests require permission_mode dontAsk")


@asynccontextmanager
async def _request_directory() -> AsyncIterator[Path]:
    temporary = tempfile.TemporaryDirectory(prefix="async-rbench-claude-")
    try:
        yield Path(temporary.name)
    finally:
        # Closing a Windows process job initiates descendant termination, but
        # their cwd/file handles can outlive the close briefly. Retry only these
        # sharing violations, after the inner process guard has been closed.
        deadline = asyncio.get_running_loop().time() + 5
        while True:
            try:
                temporary.cleanup()
                break
            except OSError as exc:
                if (os.name != "nt" or getattr(exc, "winerror", None) not in {32, 33}
                        or asyncio.get_running_loop().time() >= deadline):
                    raise
                await asyncio.sleep(0.05)


async def _run_process(config: TrackBConfig, args: list[str], input_bytes: bytes) -> dict[str, Any]:
    _validate_options(config)
    # This boundary also isolates the SDK, whose options.env otherwise merges
    # the entire parent environment into its CLI child.
    async with _request_directory() as directory:
        environment = _child_environment(config, directory)
        workspace = directory / "workspace"
        workspace.mkdir()
        process = await asyncio.create_subprocess_exec(
            *args, cwd=str(workspace), env=environment,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == "nt" else {"start_new_session": True}),
        )
        guard = None
        try:
            guard = protect_process(process)
            try:
                stdout, _stderr = await asyncio.wait_for(
                    process.communicate(input_bytes),
                    timeout=float(config.limits.get("request_timeout_sec", 180)),
                )
            except asyncio.TimeoutError as exc:
                raise RuntimeError("Claude Code model request timed out") from exc
            if process.returncode != 0:
                # Provider diagnostics may contain credentials or private input.
                raise RuntimeError(f"Claude Code process exited with code {process.returncode}")
            try:
                payload = json.loads(stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Claude Code returned invalid JSON") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("Claude Code returned invalid JSON result")
            if payload.get("is_error"):
                raise RuntimeError("Claude Code reported a failed model turn")
            return payload
        finally:
            try:
                if os.name != "nt":
                    # The leader may have exited while a descendant still owns
                    # a pipe; always terminate this request's process group.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                await terminate_process(process)
            finally:
                if guard is not None:
                    guard.close()


def _runtime_error() -> RuntimeError:
    return RuntimeError(
        "Claude Code integration requires either the `claude` executable or "
        '`pip install "async-rbench[track-b-claude]"`'
    )


async def _sdk_in_process(config: TrackBConfig, prompt: str) -> dict[str, Any]:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, ToolUseBlock, query
    except ImportError as exc:
        raise _runtime_error() from exc
    options = ClaudeAgentOptions(
        model=config.model,
        max_turns=int(config.limits.get("max_turns", 100)),
        tools=[],
        allowed_tools=[],
        setting_sources=[],
        cwd=str(Path.cwd()),
        system_prompt=_SYSTEM_PROMPT,
        permission_mode="dontAsk",
        mcp_servers={},
        extra_args={
            "strict-mcp-config": None,
            "mcp-config": '{"mcpServers":{}}',
            "disable-slash-commands": None,
            "no-session-persistence": None,
        },
    )
    results = []
    async for message in query(prompt=prompt, options=options):
        for block in getattr(message, "content", ()):
            if isinstance(block, ToolUseBlock):
                raise RuntimeError("Claude Code emitted a native tool outside the benchmark gateway")
        if isinstance(message, ResultMessage):
            if message.is_error or message.subtype != "success":
                raise RuntimeError("Claude Code reported a failed model turn")
            results.append(message)
    if len(results) != 1:
        raise RuntimeError("Claude Code must return exactly one completed model turn")
    result = results[0]
    usage = result.usage or {}
    return {
        "output_text": result.result or "",
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
    }


async def _sdk_query(config: TrackBConfig, prompt: str) -> dict[str, Any]:
    # The installed package remains importable from the empty working directory;
    # neither PYTHONPATH nor any repository configuration is inherited.
    return await _run_process(
        config,
        [sys.executable, "-m", "async_rbench.track_b.frameworks.claude_code", "--sdk-worker"],
        json.dumps({"model": config.model, "limits": config.limits, "prompt": prompt}).encode("utf-8"),
    )


async def _cli_query(config: TrackBConfig, prompt: str) -> dict[str, Any]:
    executable = shutil.which("claude")
    if executable is None:
        raise _runtime_error()
    args = [
        executable,
        "-p",
        "--output-format",
        "json",
        "--model",
        config.model,
        "--tools", "", "--setting-sources", "", "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}', "--disable-slash-commands",
        "--no-session-persistence", "--permission-mode", "dontAsk",
        "--system-prompt", _SYSTEM_PROMPT,
        "--max-turns", str(config.limits.get("max_turns", 100)),
    ]
    payload = await _run_process(config, args, prompt.encode("utf-8"))
    usage = payload.get("usage") or {}
    return {
        "output_text": str(payload.get("result") or payload.get("output_text") or ""),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
    }


async def _default_query(config: TrackBConfig, prompt: str) -> dict[str, Any]:
    if importlib.util.find_spec("claude_agent_sdk") is not None:
        return await _sdk_query(config, prompt)
    if shutil.which("claude") is not None:
        return await _cli_query(config, prompt)
    raise _runtime_error()


class ClaudeCodeRuntime:
    def __init__(self, config: TrackBConfig, query_fn: QueryFn | None = None) -> None:
        self.config = config
        self._query_fn = query_fn

    async def run(self, request: FrameworkRequest) -> FrameworkResult:
        prompt = render_protocol_prompt(request)
        raw = (
            await self._query_fn(prompt, config=self.config)
            if self._query_fn is not None
            else await _default_query(self.config, prompt)
        )
        return parse_protocol_result(
            str(raw.get("output_text") or ""),
            request,
            usage={
                "input_tokens": int(raw.get("input_tokens") or 0),
                "output_tokens": int(raw.get("output_tokens") or 0),
            },
        )


def build_runtime(config: TrackBConfig) -> ClaudeCodeRuntime:
    return ClaudeCodeRuntime(config)


if __name__ == "__main__":
    if sys.argv[1:] != ["--sdk-worker"]:
        raise SystemExit("Claude Code worker requires --sdk-worker")
    try:
        data = json.load(sys.stdin)
        worker_config = TrackBConfig(
            track="B", framework="claude-code", model=data["model"], limits=data["limits"],
        )
        json.dump(asyncio.run(_sdk_in_process(worker_config, data["prompt"])), sys.stdout)
    except Exception:
        # Keep SDK exceptions and provider stderr private to the bounded worker.
        raise SystemExit(1) from None
