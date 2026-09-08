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


def test_catalog_contains_four_public_frameworks() -> None:
    assert public_frameworks() == ("claude-code", "codex-cli", "langgraph", "openai-agents")
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
    assert result.actions[0].arguments == {
        "status": "incomplete",
        "summary": "Track B deterministic validation complete",
    }
    assert result.usage == {"input_tokens": 0, "output_tokens": 0}


def test_claude_code_runtime_normalizes_injected_query() -> None:
    async def query(prompt: str, **_: object):
        assert "solve it" in prompt
        return {"output_text": "claude result", "input_tokens": 12, "output_tokens": 4}

    request = FrameworkRequest(
        messages=_request().messages,
        tools=({"type": "function", "function": {"name": "terminal"}},),
    )
    result = asyncio.run(ClaudeCodeRuntime(_config("claude-code"), query_fn=query).run(request))

    assert result.output_text == "claude result"
    assert result.usage == {"input_tokens": 12, "output_tokens": 4}


def test_claude_code_runtime_falls_back_to_installed_cli(monkeypatch) -> None:
    calls = []

    async def cli_query(config, prompt):
        calls.append((config.model, prompt))
        return {"output_text": "cli result", "input_tokens": 5, "output_tokens": 2}

    monkeypatch.setattr("async_rbench.track_b.frameworks.claude_code.importlib.util.find_spec", lambda _: None)
    monkeypatch.setattr("async_rbench.track_b.frameworks.claude_code.shutil.which", lambda _: "claude")
    monkeypatch.setattr("async_rbench.track_b.frameworks.claude_code._cli_query", cli_query)

    result = asyncio.run(ClaudeCodeRuntime(_config("claude-code")).run(_request()))

    assert calls[0][0] == "test-model"
    assert "solve it" in calls[0][1]
    assert result.output_text == "cli result"
    assert result.usage == {"input_tokens": 5, "output_tokens": 2}


def test_framework_runtime_parses_structured_harness_actions() -> None:
    async def query(prompt: str, **_: object):
        assert "JSON" in prompt
        return {
            "output_text": '{"output_text":"checking","actions":[{"kind":"terminal","arguments":{"command":"pwd"}}]}',
            "input_tokens": 2,
            "output_tokens": 3,
        }

    request = FrameworkRequest(
        messages=_request().messages,
        tools=({"type": "function", "function": {"name": "terminal"}},),
    )
    result = asyncio.run(ClaudeCodeRuntime(_config("claude-code"), query_fn=query).run(request))

    assert result.output_text == "checking"
    assert result.actions[0].kind == "terminal"
    assert result.actions[0].arguments == {"command": "pwd"}


def test_langgraph_runtime_normalizes_injected_graph() -> None:
    class Graph:
        async def ainvoke(self, state):
            assert "solve it" in state["messages"][0]["content"]
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
