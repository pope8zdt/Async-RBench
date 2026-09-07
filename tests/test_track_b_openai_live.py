from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.contracts import FrameworkRequest
from async_rbench.track_b.frameworks.openai_agents import OpenAIAgentsRuntime


def _config(**options) -> TrackBConfig:
    return TrackBConfig(
        track="B",
        framework="openai-agents",
        model="gemini-3.8-flash",
        credential_env="TRACK_B_MOCK_API_KEY",
        limits={"max_turns": 2, "request_timeout_sec": 13, "max_output_tokens": 256},
        framework_options={"base_url": "https://mock-provider.invalid/v1", **options},
    )


@pytest.fixture
def sdk(monkeypatch):
    agents = pytest.importorskip("agents")
    openai = pytest.importorskip("openai")
    try:
        import httpx2 as httpx
    except ImportError:
        httpx = pytest.importorskip("httpx")
    monkeypatch.setenv("TRACK_B_MOCK_API_KEY", "test-only-selected-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-unselected-key")
    clients = []
    requests = []
    provider = SimpleNamespace(status_code=200)
    real_client = openai.AsyncOpenAI

    def response(request):
        requests.append(request)
        if provider.status_code != 200:
            return httpx.Response(provider.status_code, json={
                "error": {"message": "Mock provider failed", "type": "server_error"},
            })
        return httpx.Response(200, json={
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 1,
            "model": "provider-returned-model",
            "choices": [{"index": 0, "finish_reason": "stop", "logprobs": None,
                         "message": {"role": "assistant", "content": json.dumps({
                             "output_text": "checking",
                             "actions": [{"kind": "terminal", "arguments": {"command": "pwd"}}],
                         })}}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 5, "total_tokens": 22,
                      "input_tokens": 0, "output_tokens": 0},
        })

    def client(**kwargs):
        instance = real_client(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(response)),
        )
        clients.append(instance)
        return instance

    monkeypatch.setattr(openai, "AsyncOpenAI", client)
    return SimpleNamespace(
        agents=agents, openai=openai, clients=clients, requests=requests, provider=provider,
    )


@pytest.mark.parametrize("api_mode, model_class", [
    ("chat_completions", "OpenAIChatCompletionsModel"),
    ("responses", "OpenAIResponsesModel"),
])
def test_config_selects_explicit_client_and_api_model(sdk, api_mode, model_class):
    agent, _ = OpenAIAgentsRuntime(_config(api_mode=api_mode))._build()
    try:
        assert isinstance(agent.model, getattr(sdk.agents, model_class))
        assert agent.model.model == "gemini-3.8-flash"
        assert agent.tools == []
        assert agent.model_settings.max_tokens == 256
        assert len(sdk.clients) == 1
        client = sdk.clients[0]
        assert str(client.base_url) == "https://mock-provider.invalid/v1/"
        assert client.api_key == "test-only-selected-key"
        assert client.timeout == 13
        assert client.max_retries == 1
    finally:
        for client in sdk.clients:
            asyncio.run(client.close())


def test_chat_completion_uses_protocol_and_usage_without_native_tools_or_tracing(sdk, monkeypatch):
    real_run = sdk.agents.Runner.run

    async def checked_run(agent, prompt, **kwargs):
        # Check before running the real SDK, so a regression cannot start its tracer.
        assert kwargs["run_config"].tracing_disabled is True
        assert isinstance(agent.model, sdk.agents.OpenAIChatCompletionsModel)
        return await real_run(agent, prompt, **kwargs)

    monkeypatch.setattr(sdk.agents.Runner, "run", checked_run)
    request = FrameworkRequest(
        messages=({"role": "user", "content": "solve it"},),
        tools=({"type": "function", "function": {"name": "terminal"}},),
    )
    result = asyncio.run(OpenAIAgentsRuntime(_config(api_mode="chat_completions")).run(request))

    assert result.output_text == "checking"
    assert result.actions[0].kind == "terminal"
    assert result.actions[0].arguments == {"command": "pwd"}
    assert result.usage == {"input_tokens": 17, "output_tokens": 5}
    assert len(sdk.requests) == 1
    outgoing = sdk.requests[0]
    assert str(outgoing.url) == "https://mock-provider.invalid/v1/chat/completions"
    assert outgoing.headers["authorization"] == "Bearer test-only-selected-key"
    payload = json.loads(outgoing.content)
    assert payload["model"] == "gemini-3.8-flash"
    assert payload.get("tools", []) == []
    assert payload.get("max_tokens", payload.get("max_completion_tokens")) == 256
    assert "PUBLIC REQUEST JSON" in str(payload["messages"])
    assert sdk.clients[0].is_closed()


@pytest.mark.parametrize("credential_env", ["", "TRACK_B_MISSING_TEST_KEY"])
def test_missing_selected_credential_never_falls_back_to_default_account(sdk, monkeypatch, credential_env):
    monkeypatch.delenv("TRACK_B_MISSING_TEST_KEY", raising=False)
    config = TrackBConfig(
        track="B", framework="openai-agents", model="gemini-3.8-flash",
        credential_env=credential_env,
    )
    with pytest.raises(ValueError, match="credential"):
        OpenAIAgentsRuntime(config)._build()
    assert sdk.clients == []


@pytest.mark.parametrize("options", [{"api_mode": "invalid"}, {"max_retries": 2}])
def test_invalid_endpoint_options_fail_before_client_creation(sdk, options):
    with pytest.raises(ValueError):
        OpenAIAgentsRuntime(_config(**options))._build()
    assert sdk.clients == []


@pytest.mark.parametrize("max_retries, attempts", [(0, 1), (1, 2)])
def test_provider_errors_respect_retry_budget_and_close_client(sdk, max_retries, attempts):
    sdk.provider.status_code = 500
    with pytest.raises(sdk.openai.InternalServerError):
        asyncio.run(OpenAIAgentsRuntime(_config(
            api_mode="chat_completions", max_retries=max_retries,
        )).run(FrameworkRequest(messages=())))
    assert len(sdk.requests) == attempts
    assert sdk.clients[0].is_closed()


@pytest.mark.parametrize("usage, expected", [
    (SimpleNamespace(input_tokens=7, output_tokens=3, total_tokens=10),
     {"input_tokens": 7, "output_tokens": 3}),
    (SimpleNamespace(total_tokens=19), {"total_tokens": 19}),
    (SimpleNamespace(input_tokens=0, output_tokens=0, total_tokens=19), {"total_tokens": 19}),
    (None, {}),
])
def test_runner_usage_counts_tokens_once_and_preserves_total_only_fallback(usage, expected):
    async def run_agent(agent, prompt, **kwargs):
        return SimpleNamespace(final_output="done", context_wrapper=SimpleNamespace(usage=usage))

    runtime = OpenAIAgentsRuntime(_config(), agent="injected", run_agent=run_agent)
    result = asyncio.run(runtime.run(FrameworkRequest(messages=())))

    assert result.usage == expected
