import asyncio
import io

import pytest

from async_rbench.evaluation.model_backend import ModelTurn
from async_rbench.evaluation.token_usage import TokenUsageLedger
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import SubagentManager


class ControlledBackend:
    def __init__(self):
        self.release = asyncio.Event()
        self.calls = 0
        self.peak = 0
        self.live_calls = 0
        self.peak_live_calls = 0
        self.manager = None

    async def complete(self, **kwargs):
        self.calls += 1
        self.peak = max(self.peak, self.manager.active_count())
        self.live_calls += 1
        self.peak_live_calls = max(self.peak_live_calls, self.live_calls)
        try:
            await self.release.wait()
            return ModelTurn(assistant_message={"role": "assistant", "content": "done"},
                             tool_calls=[], total_tokens=1)
        finally:
            self.live_calls -= 1

    def runtime_metadata(self):
        return {}


def _manager(mode):
    backend = ControlledBackend()
    manager = SubagentManager(
        start={"agent_seed": 1, "execution_mode": mode,
               "allowed_work_units": [f"w{i}" for i in range(6)],
               "initial_wave": [{"workstream_id": f"w{i}", "task": "work"} for i in range(6)]},
        child_backend=backend, workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        config=ScaffoldConfig.from_file(None, {"backend": "scripted_test", "workspace_mode": "disabled",
                                              "max_concurrent_children": 3}),
        token_usage=TokenUsageLedger(emergency_cap=5_000_000),
    )
    backend.manager = manager
    return manager, backend


@pytest.mark.parametrize("mode", ["async", "linear"])
def test_six_initial_workstreams_never_exceed_three_live_children(mode):
    async def run():
        manager, backend = _manager(mode)
        manager.spawn_initial_wave()
        initial_peak = manager.active_count()
        assert await manager.wait_initial_wave_ready()
        backend.release.set()
        assert await manager.wait_linear_bundle(2)
        assert initial_peak <= 3
        assert backend.peak <= 3
        assert backend.calls == 6
    asyncio.run(run())


def test_initial_queue_drains_without_start_barrier_deadlock():
    async def run():
        manager, backend = _manager("async")
        manager.spawn_initial_wave()
        assert await manager.wait_initial_wave_ready()
        backend.release.set()
        assert await manager.wait_linear_bundle(2)
        assert len(manager._started_child_ids) == 6
        assert not any(e["type"] == "infrastructure_failure" for e in manager.emitter.events)
    asyncio.run(run())


def test_cancellation_releases_one_slot():
    async def run():
        manager, backend = _manager("async")
        manager.spawn_initial_wave()
        assert await manager.wait_initial_wave_ready()
        await manager.cancel("child-1", "cancelled work")
        active_after_cancel = manager.active_count()
        fourth_admitted = manager.children["child-4"].status != "queued"
        backend.release.set()
        assert await manager.wait_linear_bundle(2)
        assert active_after_cancel <= 3 and fourth_admitted
        assert manager.children["child-1"].status == "cancelled"
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["async", "linear"])
@pytest.mark.parametrize("terminal_outcome", ["timeout", "crash"])
def test_designed_terminal_stops_live_execution_before_releasing_capacity(mode, terminal_outcome):
    async def run():
        manager, backend = _manager(mode)
        manager.spawn_initial_wave()
        try:
            assert await manager.wait_initial_wave_ready()
            async def wait_for_calls(count):
                while backend.calls < count:
                    await asyncio.sleep(0)
            await asyncio.wait_for(wait_for_calls(3), 2)
            await manager.handle_delivery({
                "completion_id": "terminal:event-1", "child_id": "child-1",
                "terminal_outcome": terminal_outcome, "payload": {},
            })
            await manager.cancel("child-2", "cancel another workstream")
            await asyncio.wait_for(wait_for_calls(5), 2)
            assert backend.peak_live_calls <= 3
            assert backend.live_calls <= 3
            assert manager.children["child-1"].asyncio_task.done()
            assert manager.children["child-1"].status == "delivered"
            backend.release.set()
            assert await manager.wait_linear_bundle(2)
            assert manager.children["child-1"].status == "delivered"
            assert backend.calls == 6
        finally:
            backend.release.set()
            await manager.wait_linear_bundle(2)
    asyncio.run(run())


def test_recovery_shares_initial_child_capacity():
    async def run():
        manager, backend = _manager("async")
        manager.spawn_initial_wave()
        assert await manager.wait_initial_wave_ready()
        manager.workstream_rejections["w0"] = {"actionable": True, "reason_codes": ["missing_evidence"]}
        result = await manager.spawn("w0", "retry", [], "report", "normal")
        assert "error" not in result
        peak = manager.active_count()
        backend.release.set()
        assert await manager.wait_linear_bundle(2)
        assert peak <= 3 and backend.peak <= 3
        assert len(manager.children) == 7 and backend.calls == 7
    asyncio.run(run())


def test_batched_waits_for_all_queued_workflows():
    async def run():
        manager, backend = _manager("linear")
        manager.spawn_initial_wave()
        assert await manager.wait_initial_wave_ready()
        assert not manager.linear_bundle_ready()
        backend.release.set()
        assert await manager.wait_linear_bundle(2)
        entries = manager.build_linear_bundle()["workstreams"]
        assert [row["workstream_id"] for row in entries] == [f"w{i}" for i in range(6)]
        assert all(row["status"] == "no_submission" for row in entries)
    asyncio.run(run())
