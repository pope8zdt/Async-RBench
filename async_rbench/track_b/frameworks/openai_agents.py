from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult
from .common import parse_protocol_result, render_protocol_prompt


RunnerFn = Callable[..., Awaitable[Any]]


def _sdk_usage(result: Any) -> dict[str, int]:
    usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
    if usage is None:
        return {}
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    # The harness sums usage values: never include a total alongside its components.
    if input_tokens == 0 and output_tokens == 0 and total_tokens > 0:
        return {"total_tokens": total_tokens}
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


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
        options = self.config.framework_options
        api_mode = options.get(
            "api_mode", "chat_completions" if options.get("base_url") else "responses",
        )
        if api_mode not in {"chat_completions", "responses"}:
            raise ValueError("OpenAI Agents api_mode must be chat_completions or responses")
        max_retries = options.get("max_retries", 1)
        if type(max_retries) is not int or not 0 <= max_retries <= 1:
            raise ValueError("OpenAI Agents max_retries must be 0 or 1")
        credential_env = self.config.credential_env
        api_key = os.environ.get(credential_env, "") if credential_env else ""
        if not api_key.strip():
            raise ValueError("OpenAI Agents requires the selected credential_env to be set")
        try:
            from agents import (
                Agent,
                ModelSettings,
                OpenAIChatCompletionsModel,
                OpenAIResponsesModel,
                RunConfig,
                Runner,
            )
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                'OpenAI Agents integration requires `pip install "async-rbench[track-b-openai]"`'
            ) from exc
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=options.get("base_url") or "https://api.openai.com/v1",
            timeout=float(self.config.limits.get("request_timeout_sec", 60)),
            max_retries=max_retries,
        )
        model_type = (
            OpenAIChatCompletionsModel if api_mode == "chat_completions"
            else OpenAIResponsesModel
        )
        agent = Agent(
            name="Async-RBench Track B agent",
            instructions="Solve the public task and use only the supplied benchmark tools.",
            model=model_type(model=self.config.model, openai_client=client),
            model_settings=ModelSettings(
                max_tokens=self.config.limits.get("max_output_tokens"),
            ),
            tools=[],
        )

        async def run_agent(agent: Any, prompt: str, **kwargs: Any) -> Any:
            async with client:
                return await Runner.run(
                    agent,
                    prompt,
                    run_config=RunConfig(tracing_disabled=True),
                    **kwargs,
                )

        return agent, run_agent

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
            usage=_sdk_usage(result),
        )


def build_runtime(config: TrackBConfig) -> OpenAIAgentsRuntime:
    return OpenAIAgentsRuntime(config)
