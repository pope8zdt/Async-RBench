from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

import pytest

import async_rbench.evaluation.runner as runner_module
from async_rbench.evaluation.case_contract import find_private_fields
from async_rbench.evaluation.runner import EpisodeConfig, _make_start, run_episode
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime, _safe_name
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import (
    EpisodeTokenBudget, ReferenceScaffold,
)
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


def test_episode_token_budget_is_shared_and_fail_closed() -> None:
    # The budget is a per-episode hard ceiling shared across the main agent and
    # every concurrent child.  reserve() atomically checks-and-reserves under one
    # lock (so two concurrent reserves cannot both launch past the cap), and
    # settle() releases the unspent part of an estimate and charges the truth.
    async def exercise() -> tuple[bool, bool, int]:
        budget = EpisodeTokenBudget(10)
        first = await budget.reserve(6)
        second = await budget.reserve(5)
        return first, second, budget.remaining

    assert asyncio.run(exercise()) == (True, False, 4)

    async def settle_exercise() -> tuple[int, bool, bool]:
        budget = EpisodeTokenBudget(10)
        assert await budget.reserve(8)
        await budget.settle(8, 3)  # only 3 tokens actually used
        assert budget.remaining == 7
        fits = await budget.reserve(4)
        overflow = await budget.reserve(4)
        return budget.remaining, fits, overflow

    assert asyncio.run(settle_exercise()) == (3, True, False)


def _start(case_id: str = "data-recovery-service", mode: str = "async") -> dict:
    case_path = ROOT / "cases" / case_id / "public_case.yaml"
    case = load_case(case_path).raw
    import yaml

    task = yaml.safe_load((case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8"))
    config = EpisodeConfig(
        episode_id="test-episode", case_id=case_id, execution_mode=mode,
        guidance="incentive", agent_seed=1, adapter_command=[sys.executable],
        output_dir=ROOT / "artifacts" / "test-unused", use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _scaffold(start: dict) -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(
        None, {"backend": "scripted_test", "workspace_mode": "disabled"},
    )
    return ReferenceScaffold(
        start=start,
        config=config,
        backend=ScriptedTestBackend(),
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(),
    )


def test_safe_name_recleans_truncation_boundary() -> None:
    value = _safe_name("secure-release-0-async_6ce9da66", 26)
    assert len(value) <= 26
    assert value[-1].isalnum()


def test_episode_start_is_public_projection_only() -> None:
    start = _start()
    assert start["execution_mode"] == "async"
    assert find_private_fields(start) == []
    encoded = json.dumps(start, sort_keys=True).lower()
    for forbidden in (
        "result_kind", "event_assets", "observer_command", "validator_command",
        "hidden_checks", "invalidates_artifacts", "reopens_milestones",
        "authoritative_result_kind", "superseded_result_kind",
    ):
        assert forbidden not in encoded


def test_main_tools_expose_opaque_verification_not_commands() -> None:
    tools = _scaffold(_start()).main_tools()
    by_name = {item["function"]["name"]: item for item in tools}
    assert "verify_current_state" in by_name
    assert "run_reverification" not in by_name
    schema = by_name["verify_current_state"]["function"]["parameters"]
    assert set(schema["properties"]) == {"artifact_ids", "lineage_completion_ids"}
    assert "command" not in json.dumps(schema).lower()


def test_config_rejects_scripted_backend_for_official_api_identity() -> None:
    config = ScaffoldConfig.from_file(
        None, {"backend": "scripted_test", "workspace_mode": "disabled"},
    )
    assert config.backend == "scripted_test"
    metadata = config.public_metadata()
    assert metadata["workspace_mode"] == "disabled"


def test_async_initial_wave_has_benchmark_owned_capacity() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start("gaia2-stockholm-moveout", "async"))
        assert scaffold.config.max_concurrent_children == 3
        result = scaffold.manager.spawn_initial_wave()
        assert "error" not in result
        assert len(scaffold.manager.children) == 6
        assert scaffold.manager.active_count() == 6
        assert not any(
            record.status == "queued" for record in scaffold.manager.children.values()
        )
        assert all(record.evidence_schema for record in scaffold.manager.children.values())
        tasks = [
            record.asyncio_task for record in scaffold.manager.children.values()
            if record.asyncio_task is not None
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["linear", "async"])
def test_scripted_backend_runs_protocol3_end_to_end(
    tmp_path: Path, mode: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared: list[dict[str, list[str]]] = []

    class TrackingWorkspace(DisabledWorkspaceRuntime):
        async def prepare_event_assets(self, event_assets: dict[str, list[str]]) -> None:
            prepared.append(event_assets)

    monkeypatch.setattr(
        runner_module, "build_workspace_runtime",
        lambda start, config, event_asset_source_root=None: TrackingWorkspace(),
    )
    config = EpisodeConfig(
        episode_id=f"reference-{mode}",
        case_id="data-recovery-service",
        execution_mode=mode,
        guidance="incentive",
        agent_seed=7,
        adapter_command=[
            sys.executable,
            str(ROOT / "adapters" / "reference_scaffold_api.py"),
            "--backend", "scripted_test", "--workspace-mode", "disabled",
        ],
        output_dir=tmp_path / mode,
        use_container=False,
        timeout_sec=60,
    )
    score = asyncio.run(run_episode(ROOT, config))
    assert prepared == [{"wal_recovery": ["/app/main.db-wal"]}]
    assert score["execution_mode"] == mode
    assert score["scenario_constructed"] is True
    assert score["leaderboard_eligible"] is False
    participant = (tmp_path / mode / "participant_trace.jsonl").read_text(encoding="utf-8").lower()
    for forbidden in (
        "result_kind", "event_assets", "observer_command", "validator_command",
        "invalidates_artifacts", "reopens_milestones", "check_id", '"stale"',
    ):
        assert forbidden not in participant
    private_source = (tmp_path / mode / "event_source.jsonl").read_text(encoding="utf-8")
    assert "verification_requested" in private_source
    assert '"visibility": "kernel_private"' in private_source
