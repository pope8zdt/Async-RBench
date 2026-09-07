from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult
from .common import parse_protocol_result, render_protocol_prompt


QueryFn = Callable[..., Awaitable[dict[str, Any]]]


def _runtime_error() -> RuntimeError:
    return RuntimeError(
        "Claude Code integration requires either the `claude` executable or "
        '`pip install "async-rbench[track-b-claude]"`'
    )


async def _sdk_query(config: TrackBConfig, prompt: str) -> dict[str, Any]:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, TextBlock, query
    except ImportError as exc:
        raise _runtime_error() from exc
    options = ClaudeAgentOptions(
        model=config.model,
        max_turns=int(config.limits.get("max_turns", 100)),
        allowed_tools=[],
        setting_sources=[],
    )
    text_parts: list[str] = []
    input_tokens = 0
    output_tokens = 0
    async for message in query(prompt=prompt, options=options):
        for block in getattr(message, "content", ()):
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
        if isinstance(message, ResultMessage):
            usage = getattr(message, "usage", None) or {}
            input_tokens += int(usage.get("input_tokens", 0))
            output_tokens += int(usage.get("output_tokens", 0))
    return {
        "output_text": "\n".join(text_parts),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


async def _cli_query(config: TrackBConfig, prompt: str) -> dict[str, Any]:
    executable = shutil.which("claude")
    if executable is None:
        raise _runtime_error()
    process = await asyncio.create_subprocess_exec(
        executable,
        "-p",
        "--output-format",
        "json",
        "--model",
        config.model,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate(prompt.encode("utf-8"))
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Claude Code CLI failed: {detail}")
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Claude Code CLI returned invalid JSON") from exc
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
