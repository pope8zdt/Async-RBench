from __future__ import annotations

import asyncio
from pathlib import Path

from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.contracts import FrameworkRequest
from async_rbench.track_b.frameworks import (
    doctor_framework,
    get_framework,
    public_frameworks,
)
from async_rbench.track_b.frameworks.claude_code import ClaudeCodeRuntime
from async_rbench.track_b.frameworks.deterministic import DeterministicRuntime
from async_rbench.track_b.frameworks.langgraph import LangGraphRuntime
from async_rbench.track_b.frameworks.openai_agents import OpenAIAgentsRuntime


def _config(framework: str) -> TrackBConfig:
    return TrackBConfig(track="B", framework=framework, model="test-model")


def _request() -> FrameworkRequest:
    return FrameworkRequest(messages=({"role": "user", "content": "solve it"},))


def test_catalog_contains_three_public_frameworks() -> None:
    assert public_frameworks() == ("claude-code", "langgraph", "openai-agents")
    assert get_framework("deterministic").public is False


def test_doctor_reports_missing_optional_dependency(monkeypatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda _: None)

    report = doctor_framework("langgraph", _config("langgraph"))

    assert report.ready is False
    assert "async-rbench[track-b-langgraph]" in report.install_hint


def test_doctor_deterministic_runtime_is_always_ready() -> None:
    report = doctor_framework("deterministic", _config("deterministic"))

    assert report.ready is True
    assert report.credential_present is True


def test_deterministic_runtime_returns_stable_finish_action() -> None:
    result = asyncio.run(DeterministicRuntime(_config("deterministic")).run(_request()))

    assert result.output_text == "Track B deterministic validation complete"
    assert [action.kind for action in result.actions] == ["finish"]
    assert result.usage == {"input_tokens": 0, "output_tokens": 0}


def test_claude_code_runtime_normalizes_injected_query() -> None:
    async def query(prompt: str, **_: object):
        assert "solve it" in prompt
        return {"output_text": "claude result", "input_tokens": 12, "output_tokens": 4}

    result = asyncio.run(ClaudeCodeRuntime(_config("claude-code"), query_fn=query).run(_request()))

    assert result.output_text == "claude result"
    assert result.usage == {"input_tokens": 12, "output_tokens": 4}


def test_langgraph_runtime_normalizes_injected_graph() -> None:
    class Graph:
        async def ainvoke(self, state):
            assert state["messages"][0]["content"] == "solve it"
            return {"messages": [*state["messages"], {"role": "assistant", "content": "graph result"}]}

    result = asyncio.run(LangGraphRuntime(_config("langgraph"), graph=Graph()).run(_request()))

    assert result.output_text == "graph result"


def test_openai_agents_runtime_normalizes_injected_runner() -> None:
    class Result:
        final_output = "agents result"
        context_wrapper = None

    async def run_agent(agent, prompt, **kwargs):
        assert agent == "injected-agent"
        assert "solve it" in prompt
        assert kwargs["max_turns"] == 100
        return Result()

    runtime = OpenAIAgentsRuntime(
        _config("openai-agents"),
        agent="injected-agent",
        run_agent=run_agent,
    )
    result = asyncio.run(runtime.run(_request()))

    assert result.output_text == "agents result"
