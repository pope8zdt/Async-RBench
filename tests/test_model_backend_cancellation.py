import asyncio
import threading

import pytest

from async_rbench.evaluation.model_backend import ModelTurn, OpenAICompatibleBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig


@pytest.mark.parametrize("request_fails", [False, True])
def test_cancelled_request_keeps_capacity_until_blocking_worker_finishes(request_fails):
    async def run():
        config = ScaffoldConfig.from_file(None, {"backend": "scripted_test", "max_api_concurrency": 1})
        backend = OpenAICompatibleBackend(config)
        started = threading.Event()
        release = threading.Event()
        calls = []

        def request(payload, role):
            calls.append(role)
            if role == "first":
                started.set()
                if not release.wait(5):
                    raise TimeoutError("test worker was not released")
                if request_fails:
                    raise RuntimeError("provider failure during cancellation")
            return ModelTurn(assistant_message={"role": "assistant", "content": "done"},
                             tool_calls=[], total_tokens=1)

        backend._request = request

        async def complete(role):
            return await backend.complete(role=role, model="test", messages=[], tools=[], seed=1)

        first = asyncio.create_task(complete("first"))
        second = None
        try:
            async def wait_started():
                while not started.is_set():
                    await asyncio.sleep(0)
            await asyncio.wait_for(wait_started(), 2)
            first.cancel()
            second = asyncio.create_task(complete("second"))
            # Give cancellation and the second admission a chance to execute.
            await asyncio.sleep(0.02)
            first.cancel()
            await asyncio.sleep(0.02)
            assert not first.done(), "A live provider request still owns its child slot"
            assert calls == ["first"], "Cancellation must not release the API semaphore early"
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await first
            await asyncio.wait_for(second, 2)
            assert calls == ["first", "second"]
        finally:
            release.set()
            await asyncio.gather(first, *([second] if second else []), return_exceptions=True)

    asyncio.run(run())
