from __future__ import annotations

"""Recovery delegation is bounded by spawn policy, never token admission."""

import asyncio
import io
import json
import sys
from pathlib import Path

import yaml

from async_rbench.evaluation.runner import EpisodeConfig, _make_start
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import (
    ChildAgent, ChildRecord, ReferenceScaffold,
)
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]
WAL_TASK = "retry wal recovery with a complete report artifact"


def _start() -> dict:
    case_path = ROOT / "cases" / "data-recovery-service" / "public_case.yaml"
    case = load_case(case_path).raw
    task = yaml.safe_load(
        (case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8")
    )
    config = EpisodeConfig(
        episode_id="test-episode",
        case_id="data-recovery-service",
        execution_mode="linear",
        guidance="incentive",
        agent_seed=1,
        adapter_command=[sys.executable],
        output_dir=ROOT / "artifacts" / "test-unused",
        use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _build_manager(**overrides: object) -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "workspace_mode": "disabled",
        **overrides,
    })
    scaffold = ReferenceScaffold(
        start=_start(),
        config=config,
        backend=ScriptedTestBackend(),
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
    )
    manager = scaffold.manager
    for child_id, workstream_id in (
        ("c-wal", "wal_recovery"),
        ("c-check", "checkpoint_recovery"),
        ("c-merge", "merge_support"),
    ):
        record = ChildRecord(
            child_id=child_id,
            task="t",
            work_units=[workstream_id],
            targets=[],
            expected_output="e",
            priority="normal",
            status="completed_hidden",
            completion_id=f"comp-{child_id}",
        )
        manager.children[child_id] = record
        manager.completion_to_child[record.completion_id] = child_id
        manager.attempt_counts[workstream_id] = 1
    manager._launch_queued = lambda: None
    return scaffold


async def _reject(
    manager: object, child_id: str, workstream_id: str, code: str,
) -> None:
    await manager.handle_rejection({
        "completion_id": f"comp-{child_id}",
        "reason_codes": [code],
        "child_id": child_id,
    })
    assert manager.workstream_rejections[workstream_id]["actionable"] is True


def test_recovery_spawn_does_not_estimate_or_reserve_tokens() -> None:
    async def exercise() -> None:
        scaffold = _build_manager(emergency_total_token_cap=1)
        manager = scaffold.manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")

        result = await manager.spawn("wal_recovery", WAL_TASK, [], "", "high")

        assert "child_id" in result
        assert manager.token_usage.snapshot["total"] == 0
        record = manager.children[result["child_id"]]
        assert not hasattr(record, "initial_reservation")

    asyncio.run(exercise())


def test_second_recovery_for_workstream_is_refused_by_spawn_cap() -> None:
    async def exercise() -> None:
        scaffold = _build_manager()
        manager = scaffold.manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")

        first = await manager.spawn("wal_recovery", WAL_TASK, [], "", "high")
        assert "child_id" in first
        second = await manager.spawn("wal_recovery", WAL_TASK + " v2", [], "", "high")
        assert "error" in second
        assert "maximum recovery attempts for workstream" in second["error"]
        assert manager.recovery_spawn_counts["wal_recovery"] == 1

    asyncio.run(exercise())


def test_recovery_requires_actionable_public_rejection() -> None:
    async def exercise() -> None:
        manager = _build_manager().manager
        result = await manager.spawn(
            "merge_support", "retry merge", [], "", "high",
        )
        assert "error" in result
        assert "no actionable" in result["error"]

    asyncio.run(exercise())


def test_accepted_recovery_prompt_keeps_prior_rejection_feedback() -> None:
    async def exercise() -> None:
        manager = _build_manager().manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")
        result = await manager.spawn("wal_recovery", WAL_TASK, [], "", "high")
        record = manager.children[result["child_id"]]

        assert record.attempt_number == 2
        messages = ChildAgent.initial_messages(record)
        user_payload = json.loads(messages[1]["content"])
        assert user_payload["prior_attempt"] == {
            "failed_attempt_count": 1,
            "last_rejection": {
                "reason_codes": ["report_file_missing"],
                "contract_part": "report_file",
            },
        }

    asyncio.run(exercise())
