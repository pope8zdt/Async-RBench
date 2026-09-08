from __future__ import annotations

from typing import Any

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult
from .common import parse_protocol_result, render_protocol_prompt


def _message_text(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


class LangGraphRuntime:
    def __init__(self, config: TrackBConfig, graph: Any | None = None) -> None:
        self.config = config
        self._graph = graph

    def _build_graph(self) -> Any:
        try:
            from langchain.agents import create_agent
        except ImportError as exc:
            raise RuntimeError(
                'LangGraph integration requires `pip install "async-rbench[track-b-langgraph]"`'
            ) from exc
        return create_agent(model=self.config.model, tools=[])

    async def run(self, request: FrameworkRequest) -> FrameworkResult:
        graph = self._graph or self._build_graph()
        state = await graph.ainvoke({
            "messages": [{"role": "user", "content": render_protocol_prompt(request)}],
        })
        messages = list(state.get("messages") or [])
        text = _message_text(messages[-1]) if messages else ""
        return parse_protocol_result(text, request)


def build_runtime(config: TrackBConfig) -> LangGraphRuntime:
    return LangGraphRuntime(config)
