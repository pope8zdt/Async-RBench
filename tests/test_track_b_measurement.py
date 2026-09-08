import asyncio

from async_rbench.track_b.adapter import FrameworkModelBackend
from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.contracts import FrameworkResult


def test_backend_counts_tokens_once_and_does_not_invent_provider_identity():
    class Runtime:
        async def run(self, request):
            return FrameworkResult(
                output_text="done",
                usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            )

    backend = FrameworkModelBackend(
        TrackBConfig(track="B", framework="openai-agents", model="configured-model"),
        Runtime(),
    )
    turn = asyncio.run(backend.complete(
        role="main", model="configured-model", messages=[], tools=[], seed=2026,
    ))
    assert turn.total_tokens == 10
    assert turn.resolved_model == ""
    observation = backend.runtime_metadata()["model_observations"][0]
    assert observation["requested_model"] == "configured-model"
    assert observation["resolved_model"] == ""


def test_backend_records_provider_identity_only_when_returned():
    class Runtime:
        async def run(self, request):
            return FrameworkResult(output_text="done", resolved_model="actual-model")

    backend = FrameworkModelBackend(
        TrackBConfig(track="B", framework="openai-agents", model="configured-model"),
        Runtime(),
    )
    turn = asyncio.run(backend.complete(
        role="main", model="configured-model", messages=[], tools=[], seed=2026,
    ))
    assert turn.resolved_model == "actual-model"
