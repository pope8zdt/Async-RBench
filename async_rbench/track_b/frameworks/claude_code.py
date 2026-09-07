from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult


QueryFn = Callable[..., Awaitable[dict[str, Any]]]


def _prompt(request: FrameworkRequest) -> str:
    return json.dumps({"messages": request.messages, "tools": request.tools}, ensure_ascii=False)


async def _sdk_query(config: TrackBConfig, prompt: str) -> dict[str, Any]:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, TextBlock, query
    except ImportError as exc:
        raise RuntimeError(
            'Claude Code integration requires `pip install "async-rbench[track-b-claude]"`'
        ) from exc
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


class ClaudeCodeRuntime:
    def __init__(self, config: TrackBConfig, query_fn: QueryFn | None = None) -> None:
        self.config = config
        self._query_fn = query_fn

    async def run(self, request: FrameworkRequest) -> FrameworkResult:
        prompt = _prompt(request)
        raw = (
            await self._query_fn(prompt, config=self.config)
            if self._query_fn is not None
            else await _sdk_query(self.config, prompt)
        )
        return FrameworkResult(
            output_text=str(raw.get("output_text") or ""),
            usage={
                "input_tokens": int(raw.get("input_tokens") or 0),
                "output_tokens": int(raw.get("output_tokens") or 0),
            },
        )


def build_runtime(config: TrackBConfig) -> ClaudeCodeRuntime:
    return ClaudeCodeRuntime(config)
