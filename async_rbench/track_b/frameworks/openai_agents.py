from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult
from .common import parse_protocol_result, render_protocol_prompt


RunnerFn = Callable[..., Awaitable[Any]]


class OpenAIAgentsRuntime:
    def __init__(
        self,
        config: TrackBConfig,
        agent: Any | None = None,
        run_agent: RunnerFn | None = None,
    ) -> None:
        self.config = config
        self._agent = agent
        self._run_agent = run_agent

    def _build(self) -> tuple[Any, RunnerFn]:
        try:
            from agents import Agent, Runner
        except ImportError as exc:
            raise RuntimeError(
                'OpenAI Agents integration requires `pip install "async-rbench[track-b-openai]"`'
            ) from exc
        agent = Agent(
            name="Async-RBench Track B agent",
            instructions="Solve the public task and use only the supplied benchmark tools.",
            model=self.config.model,
            tools=[],
        )
        return agent, Runner.run

    async def run(self, request: FrameworkRequest) -> FrameworkResult:
        if self._agent is None or self._run_agent is None:
            agent, run_agent = self._build()
        else:
            agent, run_agent = self._agent, self._run_agent
        result = await run_agent(
            agent,
            render_protocol_prompt(request),
            max_turns=int(self.config.limits.get("max_turns", 100)),
        )
        return parse_protocol_result(
            str(getattr(result, "final_output", "") or ""),
            request,
        )


def build_runtime(config: TrackBConfig) -> OpenAIAgentsRuntime:
    return OpenAIAgentsRuntime(config)
