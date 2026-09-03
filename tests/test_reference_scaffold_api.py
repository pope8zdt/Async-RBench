from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

import pytest

import async_rbench.evaluation.runner as runner_module
from async_rbench.evaluation.budget import BudgetPool
from async_rbench.evaluation.case_contract import find_private_fields
from async_rbench.evaluation.model_backend import (
    ModelTurn, ToolCall, serialized_conversation_bytes,
)
from async_rbench.evaluation.runner import EpisodeConfig, _make_start, run_episode
from async_rbench.evaluation.workspace_runtime import CommandResult, DisabledWorkspaceRuntime, _safe_name
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import (
    ChildAgent, ChildRecord, EpisodeTokenBudget, ReferenceScaffold,
    build_child_user_message,
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
        # Unit tests inject an already-closed transport so any scaffold run can
        # start its reader without touching pytest's captured process stdin.
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
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


def test_completed_finish_requires_fresh_final_commit_and_verification() -> None:
    class PassingWorkspace(DisabledWorkspaceRuntime):
        async def observe_artifact(self, artifact_id: str) -> dict[str, str]:
            return {
                "observed_digest": "a" * 64,
                "observed_path": f"/app/output_data/{artifact_id}.json",
            }

        async def verify_current_state(
            self, artifact_ids: list[str], lineage_completion_ids: list[str],
        ) -> dict[str, object]:
            return {"passed": True, "checks_total": 1, "checks_passed": 1}

    async def exercise() -> None:
        scaffold = _scaffold(_start())
        scaffold.workspace = PassingWorkspace()
        artifact_id = scaffold.start["allowed_artifacts"][0]

        blocked = await scaffold._execute_main_tool(ToolCall(
            "finish-early", "finish", {"status": "completed", "summary": "too early"},
        ))
        assert blocked["error"] == "completion_preconditions_not_met"
        assert scaffold.finished is False

        committed = await scaffold._execute_main_tool(ToolCall(
            "commit-1", "commit_artifact", {
                "artifact_id": artifact_id,
                "version": "v1",
                "lineage_completion_ids": [],
                "evidence_paths": [],
                "final": True,
            },
        ))
        assert committed["committed"] is True
        verified = await scaffold._execute_main_tool(ToolCall(
            "verify-1", "verify_current_state", {
                "artifact_ids": [artifact_id], "lineage_completion_ids": [],
            },
        ))
        assert verified["passed"] is True

        completion_id = "completion-authority"
        scaffold.manager.children["child-authority"] = ChildRecord(
            child_id="child-authority",
            task="authority",
            work_units=[],
            targets=[],
            expected_output="authority",
            priority="high",
            status="delivered",
            completion_id=completion_id,
            delivery={"completion_id": completion_id},
        )
        scaffold.manager.completion_to_child[completion_id] = "child-authority"
        accepted = await scaffold._execute_main_tool(ToolCall(
            "accept-1", "acknowledge_result", {
                "completion_id": completion_id,
                "decision": "use",
                "reason": "authoritative evidence",
            },
        ))
        assert accepted["decision"] == "use"

        stale_finish = await scaffold._execute_main_tool(ToolCall(
            "finish-stale", "finish", {"status": "completed", "summary": "stale closure"},
        ))
        assert stale_finish["error"] == "completion_preconditions_not_met"
        assert len(stale_finish["missing"]) == 2

        await scaffold._execute_main_tool(ToolCall(
            "commit-2", "commit_artifact", {
                "artifact_id": artifact_id,
                "version": "v2",
                "lineage_completion_ids": [completion_id],
                "evidence_paths": [],
                "final": True,
            },
        ))
        await scaffold._execute_main_tool(ToolCall(
            "verify-2", "verify_current_state", {
                "artifact_ids": [artifact_id],
                "lineage_completion_ids": [completion_id],
            },
        ))
        finished = await scaffold._execute_main_tool(ToolCall(
            "finish-good", "finish", {"status": "completed", "summary": "closed"},
        ))
        assert finished == {"ending": True, "status": "completed"}
        assert scaffold.finished is True

    asyncio.run(exercise())


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
    adapter_command = [
        sys.executable,
        str(ROOT / "adapters" / "reference_scaffold_api.py"),
        "--backend", "scripted_test", "--workspace-mode", "disabled",
    ]
    if mode == "linear":
        # The scripted conformance controller only parses ASYNC_RBENCH_DELIVERY
        # messages, not the new ASYNC_RBENCH_LINEAR_BUNDLE. Linear presents ONE
        # atomic bundle (spec §6) so the scripted main cannot act on it; cap the
        # turn budget so the conformance run terminates quickly.
        config_path = tmp_path / "linear_config.yaml"
        config_path.write_text("max_main_turns: 5\n", encoding="utf-8")
        adapter_command += ["--config", str(config_path)]
    config = EpisodeConfig(
        episode_id=f"reference-{mode}",
        case_id="data-recovery-service",
        execution_mode=mode,
        guidance="incentive",
        agent_seed=7,
        adapter_command=adapter_command,
        output_dir=tmp_path / mode,
        use_container=False,
        timeout_sec=60,
    )
    score = asyncio.run(run_episode(ROOT, config))
    assert prepared == [{"wal_recovery": ["/app/main.db-wal"]}]
    assert score["execution_mode"] == mode
    assert score["scenario_constructed"] is True
    assert score["leaderboard_eligible"] is False
    # The runtime's final per-pool snapshot must survive to the score record:
    # settled / remaining / overrun / halt reason per pool (spec §7).
    assert score["budget_report"] is not None
    assert set(score["budget_report"]) == {
        "child_shared", "main_pre", "main_post", "main_total",
    }
    participant = (tmp_path / mode / "participant_trace.jsonl").read_text(encoding="utf-8").lower()
    for forbidden in (
        "result_kind", "event_assets", "observer_command", "validator_command",
        "invalidates_artifacts", "reopens_milestones", "check_id", '"stale"',
    ):
        assert forbidden not in participant
    private_source = (tmp_path / mode / "event_source.jsonl").read_text(encoding="utf-8")
    if mode == "async":
        assert "verification_requested" in private_source
    else:
        # Linear presents one atomic bundle: the ready/presented boundaries are
        # recorded and no per-result presentation boundary may appear.
        assert "linear_bundle_ready" in private_source
        assert "linear_bundle_presented" in private_source
        assert "\"result_presented\"" not in private_source
        # Item-5 regression: Linear must actually call Main after the bundle.
        # The pre-fix barrier fired at the 180s terminal-command cap while the
        # scripted children were completing, so these episodes ended with
        # main_tokens=0 and were still reported scored.  A fixed (scripted)
        # child must yield a contract-acceptable result, the bundle must be
        # presented, and Main must then be called at least once.
        assert score["main_tokens"] > 0
        assert score["child_tokens"] > 0
        # The fixed child's result reached the wave as a delivered bundle entry.
        assert "\"result_delivered\"" in private_source
    assert '"visibility": "kernel_private"' in private_source


def test_initial_wave_asset_staging_failure_is_unscored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The complete initial-wave startup must not silently score a broken episode.

    Regression for the async=None episodes where an event asset failed to stage
    into an initial-wave child's container: the benchmark constructed no usable
    scenario and the episode carried an infrastructure_failure (component
    ``child_start``), so it must be unscored rather than measured as X=0.
    """
    class FailingStagingWorkspace(DisabledWorkspaceRuntime):
        async def stage_child_assets(
            self, child_id: str, work_units: list[str], event_assets: dict[str, list[str]],
        ) -> None:
            raise RuntimeError("simulated event asset staging failure")

    monkeypatch.setattr(
        runner_module, "build_workspace_runtime",
        lambda start, config, event_asset_source_root=None: FailingStagingWorkspace(),
    )
    config = EpisodeConfig(
        episode_id="reference-failstage",
        case_id="data-recovery-service",
        execution_mode="async",
        guidance="incentive",
        agent_seed=7,
        adapter_command=[
            sys.executable,
            str(ROOT / "adapters" / "reference_scaffold_api.py"),
            "--backend", "scripted_test", "--workspace-mode", "disabled",
        ],
        output_dir=tmp_path / "failstage",
        use_container=False,
        timeout_sec=60,
    )
    score = asyncio.run(run_episode(ROOT, config))
    assert score["score_status"] == "unscored"
    assert score["scenario_constructed"] is False
    infra = score.get("infrastructure_failures") or []
    assert any(failure.get("component") == "child_start" for failure in infra), infra


def _inject_delivery(
    scaffold: ReferenceScaffold, child_id: str, completion_id: str,
) -> None:
    """Register a child/completion pair and route one delivery through the adapter
    queue so the FIFO presentation path is exercised."""
    scaffold.manager.children[child_id] = ChildRecord(
        child_id=child_id, task="work", work_units=["ws"], targets=[],
        expected_output="out", priority="high", status="completed_hidden",
        completion_id=completion_id,
    )
    scaffold.manager.completion_to_child[completion_id] = child_id


def test_subagent_manager_enqueues_deliveries_in_fifo_receive_order() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start())
        _inject_delivery(scaffold, "child-2", "compl-2")
        _inject_delivery(scaffold, "child-1", "compl-1")
        await scaffold.manager.handle_delivery(
            {"completion_id": "compl-2", "payload": {"id": 2}},
        )
        await scaffold.manager.handle_delivery(
            {"completion_id": "compl-1", "payload": {"id": 1}},
        )
        # FIFO by adapter receive order (compl-2 arrived first).
        first = scaffold.manager.select_presentable()
        assert first is not None
        assert first.completion_id == "compl-2"
        scaffold.manager.mark_presented(first.occurrence_id, turn_id="t1", window_id="w1")
        # A queued occurrence is sealed while the response window is open.
        assert scaffold.manager.select_presentable() is None
        # Once the window hits max_response_turns it closes and unseals next.
        for _ in range(4):
            scaffold.manager.presentation_queue.record_turn()
        assert scaffold.manager.presentation_queue.close_active_window() is True
        second = scaffold.manager.select_presentable()
        assert second is not None
        assert second.completion_id == "compl-1"
        assert second.payload["completion_id"] == "compl-1"

    asyncio.run(exercise())


def test_finish_guard_rejects_queued_occurrence_and_open_window() -> None:
    class PassingWorkspace(DisabledWorkspaceRuntime):
        async def observe_artifact(self, artifact_id: str) -> dict[str, str]:
            return {
                "observed_digest": "a" * 64,
                "observed_path": f"/app/output_data/{artifact_id}.json",
            }

        async def verify_current_state(
            self, artifact_ids: list[str], lineage_completion_ids: list[str],
        ) -> dict[str, object]:
            return {"passed": True, "checks_total": 1, "checks_passed": 1}

    async def exercise() -> None:
        scaffold = _scaffold(_start())
        scaffold.workspace = PassingWorkspace()
        artifact_id = scaffold.start["allowed_artifacts"][0]
        # Bring the commit + verification preconditions to satisfied so the only
        # outstanding precondition is a queued occurrence / open response window.
        await scaffold._execute_main_tool(ToolCall(
            "commit-1", "commit_artifact", {
                "artifact_id": artifact_id, "version": "v1",
                "lineage_completion_ids": [], "evidence_paths": [], "final": True,
            },
        ))
        await scaffold._execute_main_tool(ToolCall(
            "verify-1", "verify_current_state", {
                "artifact_ids": [artifact_id], "lineage_completion_ids": [],
            },
        ))

        # A queued, adapter-received-but-unpresented occurrence blocks completion.
        _inject_delivery(scaffold, "child-queue", "compl-queue")
        await scaffold.manager.handle_delivery(
            {"completion_id": "compl-queue", "payload": {"id": 1}},
        )
        blocked = await scaffold._execute_main_tool(ToolCall(
            "finish-queued", "finish", {"status": "completed", "summary": "s"},
        ))
        assert blocked["error"] == "completion_preconditions_not_met"
        assert blocked["missing"] == [
            "all delivered occurrences presented and response windows closed",
        ]

        # Presenting it opens a response window, which still blocks completion.
        candidate = scaffold.manager.select_presentable()
        assert candidate is not None
        scaffold.manager.mark_presented(candidate.occurrence_id, turn_id="t1", window_id="w1")
        blocked_window = await scaffold._execute_main_tool(ToolCall(
            "finish-window", "finish", {"status": "completed", "summary": "s"},
        ))
        assert blocked_window["error"] == "completion_preconditions_not_met"

        # Once the window closes deterministically, completion is allowed.
        for _ in range(4):
            scaffold.manager.presentation_queue.record_turn()
        assert scaffold.manager.presentation_queue.close_active_window() is True
        finished = await scaffold._execute_main_tool(ToolCall(
            "finish-ok", "finish", {"status": "completed", "summary": "closed"},
        ))
        assert finished == {"ending": True, "status": "completed"}

    asyncio.run(exercise())


def test_finish_guard_rejects_incomplete_finish_while_occurrence_queued() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start())
        # A queued, adapter-received-but-unpresented occurrence also blocks an
        # *incomplete* finish: the guard is deliberately status-agnostic (spec
        # §5.1(6), §9.4), so a participant cannot quietly surrender past a
        # delivery that never reached a main-model request.
        _inject_delivery(scaffold, "child-inc", "compl-inc")
        await scaffold.manager.handle_delivery(
            {"completion_id": "compl-inc", "payload": {"id": 1}},
        )
        blocked = await scaffold._execute_main_tool(ToolCall(
            "finish-inc-blocked", "finish", {"status": "incomplete", "summary": "s"},
        ))
        assert blocked["error"] == "completion_preconditions_not_met"
        assert blocked["missing"] == [
            "all delivered occurrences presented and response windows closed",
        ]
        assert scaffold.finished is False

        # Presenting opens a window; an incomplete finish is still refused while
        # the window is unclosed.
        candidate = scaffold.manager.select_presentable()
        assert candidate is not None
        scaffold.manager.mark_presented(
            candidate.occurrence_id, turn_id="t1", window_id="w1",
        )
        blocked_window = await scaffold._execute_main_tool(ToolCall(
            "finish-inc-window", "finish", {"status": "incomplete", "summary": "s"},
        ))
        assert blocked_window["error"] == "completion_preconditions_not_met"
        assert scaffold.finished is False

        # Once the window closes deterministically, an incomplete finish is
        # accepted (no commit/verify preconditions apply to incomplete).
        for _ in range(4):
            scaffold.manager.presentation_queue.record_turn()
        assert scaffold.manager.presentation_queue.close_active_window() is True
        finished = await scaffold._execute_main_tool(ToolCall(
            "finish-inc-ok", "finish", {"status": "incomplete", "summary": "closed"},
        ))
        assert finished == {"ending": True, "status": "incomplete"}
        assert scaffold.finished is True

    asyncio.run(exercise())


# --- Task 5: Linear true-concurrency sync aggregation (spec §6) -------------
#
# Linear runs the benchmark-owned wave concurrently (same as async) but shows the
# main model ONE atomic bundle at the end, sorted by workstream_id, carrying
# success / contract rejection / designed failure / timeout / cancellation. It
# emits no per-result result_presented and never computes DRS. These tests drive
# the SubagentManager aggregation and the runtime presentation seam directly.


def _register_linear_children(manager, pairs: list[tuple[str, str]]) -> None:
    """Register one ChildRecord per (child_id, workstream_id) with a completion."""
    for index, (child_id, workstream_id) in enumerate(pairs):
        record = ChildRecord(
            child_id=child_id, task="t", work_units=[workstream_id], targets=[],
            expected_output="e", priority="normal", status="completed_hidden",
            completion_id=f"comp-{child_id}",
        )
        manager.children[child_id] = record
        manager.completion_to_child[f"comp-{child_id}"] = child_id


def test_linear_bundle_is_atomic_mixed_and_participant_safe() -> None:
    """Linear aggregates one terminal bundle; never a per-result presentation."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "linear"))
        manager = scaffold.manager
        _register_linear_children(manager, [
            ("c-wal", "wal_recovery"),
            ("c-check", "checkpoint_recovery"),
            ("c-merge", "merge_support"),
        ])
        await manager.handle_delivery({
            "completion_id": "comp-c-wal", "payload": {"i": 1},
            "payload_sha256": "a" * 64, "child_id": "c-wal",
        })
        await manager.handle_delivery({
            "completion_id": "comp-c-check", "payload": {"i": 2},
            "payload_sha256": "b" * 64, "child_id": "c-check",
        })
        await manager.handle_rejection({
            "completion_id": "comp-c-merge",
            "reason_codes": ["missing_required_evidence"], "child_id": "c-merge",
        })

        # Linear never enqueues a per-result occurrence nor emits a per-result
        # presentation boundary (individual_result_presentations == 0).
        assert manager.presentation_queue.has_pending() is False
        assert not any(
            e.get("type") in {"result_presented", "adapter_queued", "result_available"}
            for e in scaffold.emitter.events
        )
        assert manager.linear_bundle_ready() is True

        bundle = manager.build_linear_bundle()
        workstreams = bundle["workstreams"]
        assert [item["workstream_id"] for item in workstreams] == sorted(
            item["workstream_id"] for item in workstreams
        )
        statuses = {item["workstream_id"]: item["status"] for item in workstreams}
        assert statuses == {
            "checkpoint_recovery": "delivered",
            "merge_support": "contract_rejected",
            "wal_recovery": "delivered",
        }
        # No evaluator-private event role leaks into the bundle.
        encoded = json.dumps(bundle).lower()
        for forbidden in (
            "result_kind", "authoritative_result_kind", "superseded_result_kind",
            "invalidates_artifacts", "reopens_milestones", "evaluator_stale",
            "controlled_order", "benchmark_event_id",
        ):
            assert forbidden not in encoded
        wal = next(item for item in workstreams if item["workstream_id"] == "wal_recovery")
        assert wal["result"]["type"] == "result_delivered"
        assert wal["result"]["workstream_id"] == "wal_recovery"
        merge = next(item for item in workstreams if item["workstream_id"] == "merge_support")
        assert merge["rejection"]["type"] == "result_rejected"

    asyncio.run(exercise())


def test_linear_bundle_presented_once_and_message_injected() -> None:
    """A terminal wave yields ONE linear_bundle_ready / linear_bundle_presented."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "linear"))
        manager = scaffold.manager
        _register_linear_children(manager, [("c-wal", "wal_recovery")])
        await manager.handle_delivery({
            "completion_id": "comp-c-wal", "payload": {"i": 1},
            "payload_sha256": "a" * 64, "child_id": "c-wal",
        })
        assert await scaffold._maybe_present_linear_bundle() is True
        types = [e.get("type") for e in scaffold.emitter.events]
        assert types.count("linear_bundle_ready") == 1
        assert types.count("linear_bundle_presented") == 1
        assert any(
            str(m.get("content", "")).startswith("ASYNC_RBENCH_LINEAR_BUNDLE")
            for m in scaffold.messages
        )
        # No per-result presentation boundary was emitted for the bundle.
        assert "result_presented" not in types

    asyncio.run(exercise())


def test_linear_bundle_wait_cap_is_the_child_lifecycle_not_the_terminal_cap() -> None:
    """Regression: the barrier used to wait only ``child_terminal_timeout_sec``
    (180s) while a child's lifecycle runs to ``child_timeout_sec`` (900s+), so a
    healthy wave was declared "did not reach a terminal bundle" and the episode
    ended with main_tokens=0 yet reported scored.  The wait cap must be the full
    benchmark-owned child lifecycle (start barrier + child timeout), and a
    genuine timeout must be recorded as an infrastructure failure."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "linear"))
        config = scaffold.config
        recorded: list[float] = []

        async def fake_wait(timeout: float) -> bool:
            recorded.append(timeout)
            return False

        scaffold.manager.wait_linear_bundle = fake_wait
        result = await scaffold._maybe_present_linear_bundle()
        assert result is False
        assert recorded == [config.start_barrier_timeout_sec + config.child_timeout_sec]
        # The failure must be an infrastructure failure, not a silent
        # ``incomplete`` that the scorer keeps as ``scored`` with main_tokens=0.
        failures = [
            event for event in scaffold.emitter.events
            if event.get("type") == "infrastructure_failure"
        ]
        assert len(failures) == 1
        assert failures[0]["component"] == "linear_bundle_barrier"

    asyncio.run(exercise())


def test_main_budget_refusal_emits_distinguishing_event_and_snapshot() -> None:
    """A refused main admission records why (insufficient vs halted) and the
    final per-pool snapshot is persisted on the same termination path."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "async"))
        scaffold.budget_ledger.pool("main_pre").maximum = 0
        await scaffold.run()
        await scaffold.shutdown()
        assert scaffold.finish_status == "budget_exhausted"
        exhaustions = [
            event for event in scaffold.emitter.events
            if event.get("type") == "budget_exhausted"
        ]
        assert len(exhaustions) == 1
        assert exhaustions[0]["pool"] == "main_pre"
        assert exhaustions[0]["refusal_reason"] == "insufficient_remaining"
        assert exhaustions[0]["halt_reason"] is None
        snapshots = [
            event.get("pools", {}) for event in scaffold.emitter.events
            if event.get("type") == "budget_ledger_snapshot"
        ]
        assert len(snapshots) == 1
        assert set(snapshots[0]) == {
            "child_shared", "main_pre", "main_post", "main_total",
        }
        for pool_name in ("main_pre", "main_post", "child_shared"):
            pool = snapshots[0][pool_name]
            assert "settled" in pool and "remaining" in pool
            assert "overrun" in pool and "halt_reason" in pool
            assert "refusal_reason" in pool and "accounting_mode" in pool
        assert snapshots[0]["main_pre"]["remaining"] == 0

    asyncio.run(exercise())


def test_async_delivery_lifecycle_emits_available_then_queue_then_window_close() -> None:
    """Async delivery order: result_available -> adapter_queued -> ... ->
    response_window_closed (spec §3.2/§3.3 replay contract)."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "async"))
        manager = scaffold.manager
        _register_linear_children(manager, [("c1", "wal_recovery")])
        await manager.handle_delivery({
            "completion_id": "comp-c1", "payload": {"i": 1},
            "payload_sha256": "a" * 64, "child_id": "c1",
        })
        candidate = manager.select_presentable()
        assert candidate is not None
        types = [e.get("type") for e in scaffold.emitter.events]
        # The occurrence was made available before the adapter claimed it.
        assert types.index("result_available") < types.index("adapter_queued")
        # Present it, run the response window to max turns, then close: the
        # closure boundary must be emitted.
        manager.mark_presented(candidate.occurrence_id, turn_id="t1", window_id="w1")
        assert manager.presentation_queue.active_window is not None
        for _ in range(4):
            manager.presentation_queue.record_turn()
        scaffold._close_presentation_window()
        assert any(e.get("type") == "response_window_closed" for e in scaffold.emitter.events)
        assert manager.presentation_queue.active_window is None

    asyncio.run(exercise())


# --- P0-8 / P0-9: rejection feedback on re-delegation and its bounds ---------


def test_rejection_events_carry_attempt_count_and_contract_part() -> None:
    """A contract rejection records the failed-attempt count and the contract
    part to repair, and the async status surface (the way the main model learns
    of the rejection) exposes the same public feedback."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "async"))
        manager = scaffold.manager
        _register_linear_children(manager, [("c-1", "wal_recovery")])
        manager.attempt_counts["wal_recovery"] = 1
        await manager.handle_rejection({
            "completion_id": "comp-c-1",
            "reason_codes": ["missing_required_evidence"],
            "child_id": "c-1",
        })
        rejection = manager.children["c-1"].contract_rejection
        assert rejection["attempt_count"] == 1
        status = manager.statuses()[0]
        assert status["status"] == "contract_rejected"
        assert status["contract_rejection_reason_codes"] == ["missing_required_evidence"]
        assert status["contract_part"] == "evidence"
        assert status["attempt_count"] == 1
        stored = manager.workstream_rejections["wal_recovery"]
        assert stored["contract_part"] == "evidence"
        assert stored["actionable"] is True

    asyncio.run(exercise())


def test_replacement_spawn_carries_prior_rejection_feedback() -> None:
    """A replacement child for a rejected workstream carries the original
    workstream id, the last public error code, the failed attempt count and the
    contract part to fix."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "linear"))
        manager = scaffold.manager
        _register_linear_children(manager, [
            ("c-wal", "wal_recovery"), ("c-check", "checkpoint_recovery"),
            ("c-merge", "merge_support"),
        ])
        await manager.handle_delivery({
            "completion_id": "comp-c-check", "payload": {"i": 2},
            "payload_sha256": "b" * 64, "child_id": "c-check",
        })
        await manager.handle_delivery({
            "completion_id": "comp-c-merge", "payload": {"i": 3},
            "payload_sha256": "c" * 64, "child_id": "c-merge",
        })
        # The initial wave counted one attempt for wal_recovery (as a real
        # spawn_initial_wave would) before its child got rejected.
        manager.attempt_counts["wal_recovery"] = 1
        await manager.handle_rejection({
            "completion_id": "comp-c-wal",
            "reason_codes": ["report_file_missing"], "child_id": "c-wal",
        })
        manager._launch_queued = lambda: None  # keep the replacement un-run
        result = await manager.spawn(
            "wal_recovery", "retry with a complete report artifact", [], "", "high",
        )
        assert "child_id" in result
        record = manager.children[result["child_id"]]
        assert record.work_units == ["wal_recovery"]
        assert record.attempt_number == 2
        assert record.prior_attempt_rejection["reason_codes"] == ["report_file_missing"]
        assert record.prior_attempt_rejection["contract_part"] == "report_file"

    asyncio.run(exercise())


def test_spawn_refuses_without_actionable_feedback() -> None:
    """P0-9: a workstream whose last rejection carried no public code cannot be
    blindly re-delegated."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "linear"))
        manager = scaffold.manager
        _register_linear_children(manager, [
            ("c-wal", "wal_recovery"), ("c-check", "checkpoint_recovery"),
            ("c-merge", "merge_support"),
        ])
        await manager.handle_delivery({
            "completion_id": "comp-c-check", "payload": {"i": 2},
            "payload_sha256": "b" * 64, "child_id": "c-check",
        })
        await manager.handle_delivery({
            "completion_id": "comp-c-merge", "payload": {"i": 3},
            "payload_sha256": "c" * 64, "child_id": "c-merge",
        })
        await manager.handle_rejection({
            "completion_id": "comp-c-wal",
            "reason_codes": ["validator_command_failed"], "child_id": "c-wal",
        })
        manager._launch_queued = lambda: None
        result = await manager.spawn("wal_recovery", "try again", [], "", "high")
        assert "no actionable" in result["error"]

    asyncio.run(exercise())


def test_spawn_refuses_without_new_evidence_and_below_one_call_budget() -> None:
    """P0-9: re-delegation is bounded to one no-new-evidence retry and refused
    once the remaining child budget cannot cover one full child call."""
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "linear"))
        manager = scaffold.manager
        _register_linear_children(manager, [
            ("c-wal", "wal_recovery"), ("c-check", "checkpoint_recovery"),
            ("c-merge", "merge_support"),
        ])
        await manager.handle_delivery({
            "completion_id": "comp-c-check", "payload": {"i": 2},
            "payload_sha256": "b" * 64, "child_id": "c-check",
        })
        await manager.handle_delivery({
            "completion_id": "comp-c-merge", "payload": {"i": 3},
            "payload_sha256": "c" * 64, "child_id": "c-merge",
        })
        await manager.handle_rejection({
            "completion_id": "comp-c-wal",
            "reason_codes": ["report_payload_field_mismatch"], "child_id": "c-wal",
        })
        manager._launch_queued = lambda: None

        manager.no_new_evidence_retries["wal_recovery"] = 1
        result = await manager.spawn("wal_recovery", "try again", [], "", "high")
        assert "no new evidence" in result["error"]

        manager.no_new_evidence_retries["wal_recovery"] = 0
        pool = manager.token_budget
        pool.settled += pool.maximum  # remaining == 0
        result = await manager.spawn("wal_recovery", "try again", [], "", "high")
        assert "below one full child call" in result["error"]

    asyncio.run(exercise())


def test_no_new_evidence_retry_is_recorded_and_emitted() -> None:
    """A sealed submission repeating a prior attempt's evidence marks a
    no-information retry; different evidence does not."""
    async def exercise() -> None:
        scaffold = _scaffold(_start())
        manager = scaffold.manager
        payload = {"summary": "s", "evidence": {"finding": "x"}, "files": []}
        manager._record_workstream_evidence("wal_recovery", payload, "c-1")
        assert manager.no_new_evidence_retries["wal_recovery"] == 0
        manager._record_workstream_evidence("wal_recovery", payload, "c-2")
        assert manager.no_new_evidence_retries["wal_recovery"] == 1
        events = [
            event for event in scaffold.emitter.events
            if event.get("type") == "no_information_retry_detected"
        ]
        assert len(events) == 1
        assert events[0]["workstream_id"] == "wal_recovery"
        assert events[0]["no_new_evidence_retries"] == 1
        manager._record_workstream_evidence(
            "wal_recovery",
            {"summary": "s", "evidence": {"finding": "y"}, "files": []},
            "c-3",
        )
        assert manager.no_new_evidence_retries["wal_recovery"] == 1

    asyncio.run(exercise())


def test_replacement_child_message_carries_prior_attempt_feedback() -> None:
    """P0-8: the child instruction block for a replacement carries the failed
    attempt count and the last rejection feedback to repair."""
    from async_rbench.profiles.reference_scaffold_api.runtime import (
        build_child_user_message,
    )
    record = ChildRecord(
        child_id="c", task="t", work_units=["ws"], targets=[],
        expected_output="e", priority="high", attempt_number=2,
        prior_attempt_rejection={
            "reason_codes": ["report_file_missing"],
            "contract_part": "report_file",
        },
    )
    message = build_child_user_message(record)
    assert message["prior_attempt"] == {
        "failed_attempt_count": 1,
        "last_rejection": {
            "reason_codes": ["report_file_missing"],
            "contract_part": "report_file",
        },
    }
    fresh = build_child_user_message(ChildRecord(
        child_id="c", task="t", work_units=["ws"], targets=[],
        expected_output="e", priority="high",
    ))
    assert "prior_attempt" not in fresh


# --- P1-11 / P1-12: bounded child exploration + public pre-submit validator ---


def test_child_tools_expose_pre_submit_validator() -> None:
    names = {item["function"]["name"] for item in ChildAgent.tools()}
    assert {"terminal", "submit_result", "validate_result"} <= names


def test_child_message_carries_report_artifact_template() -> None:
    record = ChildRecord(
        child_id="c", task="t", work_units=["ws"], targets=[],
        expected_output="e", priority="high",
        public_result_contract={
            "kind": "report_file",
            "report_file": {
                "path": "/app/out.json", "must_exist": True,
                "must_be_valid_json": True,
                "fields_equal_evidence": ["finding", "revision_sha256"],
            },
        },
    )
    message = build_child_user_message(record)
    assert message["report_artifact_template"] == {
        "path": "/app/out.json",
        "must_exist": True,
        "must_be_valid_json": True,
        "fields_equal_evidence": ["finding", "revision_sha256"],
    }
    plain = build_child_user_message(ChildRecord(
        child_id="c", task="t", work_units=["ws"], targets=[],
        expected_output="e", priority="high",
    ))
    assert "report_artifact_template" not in plain


class _ValidateThenSubmitBackend:
    """Turn 1 calls validate_result; on seeing the dry-run verdict it submits a
    (nominally corrected) result.  Records every tool message it was shown."""

    def __init__(self) -> None:
        self.seen_tool_results: list[str] = []

    def runtime_metadata(self) -> dict:
        return {"model_observations": []}

    @staticmethod
    def _tool_call(call_id: str, name: str, arguments: dict) -> ModelTurn:
        raw = [{"id": call_id, "type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments, sort_keys=True),
        }}]
        return ModelTurn(
            assistant_message={"role": "assistant", "content": None, "tool_calls": raw},
            tool_calls=[ToolCall(call_id, name, arguments)],
            total_tokens=7,
        )

    async def complete(self, *, role, model, messages, tools, seed) -> ModelTurn:
        self.seen_tool_results.extend(
            str(m.get("content", "")) for m in messages if m.get("role") == "tool"
        )
        used = {
            call.get("function", {}).get("name")
            for m in messages
            for call in m.get("tool_calls") or []
            if m.get("role") == "assistant"
        }
        if "validate_result" in used:
            return self._tool_call("c-submit", "submit_result", {
                "summary": "result",
                "result_kind_hint": "recovered",
                "evidence": {
                    "report_path": "/app/out.json",
                    "finding": "recovered",
                    "revision_sha256": "0" * 64,
                },
                "files": ["/app/out.json"],
            })
        return self._tool_call("c-validate", "validate_result", {
            "summary": "result",
            "evidence": {
                "report_path": "/app/out.json",
                "finding": "recovered",
                "revision_sha256": "0" * 64,
            },
            "files": ["/app/out.json"],
        })


class _FixtureWorkspace:
    """Dry-run sees a missing report; the subsequent submit sees it repaired."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult:
        self.calls.append((child_id, command, timeout))
        if len(self.calls) == 1:
            return CommandResult(1, "ASYNC_RBENCH_CONTRACT_FAIL:report_file_missing\n")
        return CommandResult(0, "")


def test_pre_submit_validate_result_dry_runs_the_public_rule() -> None:
    """validate_result executes the deterministic render of the *public* accept
    rule (never a private validator) and reports the granular public code."""
    async def exercise() -> None:
        workspace = _FixtureWorkspace()
        backend = _ValidateThenSubmitBackend()
        config = ScaffoldConfig.from_file(
            None, {"backend": "scripted_test", "workspace_mode": "disabled"},
        )
        record = ChildRecord(
            child_id="child-1", task="produce report", work_units=["ws"],
            targets=[], expected_output="report", priority="high",
            required_evidence_fields=["report_path", "finding", "revision_sha256"],
            evidence_schema={
                "report_path": {"type": "string"},
                "finding": {"type": "string"},
                "revision_sha256": {"type": "string"},
            },
            allowed_result_files=["/app/out.json"],
            required_result_files=["/app/out.json"],
            public_result_contract={
                "kind": "report_file",
                "report_file": {
                    "path": "/app/out.json", "must_exist": True,
                    "must_be_valid_json": True,
                    "fields_equal_evidence": ["finding", "revision_sha256"],
                },
            },
            result_file_contract_enforced=True,
        )
        agent = ChildAgent(
            backend, workspace, config,
            ProtocolEmitter(stdout=io.StringIO()),
            BudgetPool("child_shared", maximum=500_000),
        )
        outcome = await agent.run(record, "test-model", 1)
        assert len(workspace.calls) == 2
        _, command, _ = workspace.calls[0]
        assert command.startswith("export ASYNC_RBENCH_RESULT_PAYLOAD_B64=")
        assert "ASYNC_RBENCH_CONTRACT_FAIL" in command
        verdicts = [c for c in backend.seen_tool_results if '"valid"' in c]
        assert len(verdicts) == 1
        verdict = json.loads(verdicts[0])
        assert verdict["valid"] is False
        assert verdict["reason_codes"] == ["report_file_missing"]
        assert verdict["contract_part"] == "report_file"
        # submit_result re-runs the same public validator instead of trusting
        # that the child called validate_result earlier.
        assert workspace.calls[1][1] == workspace.calls[0][1]
        # The child used the verdict and sealed a corrected result.
        assert outcome.kind == "submitted"
        assert outcome.payload is not None
        assert outcome.payload["evidence"]["finding"] == "recovered"
        assert outcome.hint == "recovered"

    asyncio.run(exercise())


# --- P1-13: child context length control ------------------------------------


def test_child_context_is_compressed_within_budget() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "content": "a" * 5000},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "content": "b" * 5000},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "content": "c" * 5000},
    ]
    compressed = ChildAgent._compress_messages(
        messages,
        context_budget_chars=8000,
        keep_recent=1,
        max_old_tool_content_chars=100,
    )
    # The newest complete assistant/tool block is untouched; older tool output
    # is excerpted until the full serialized wire payload fits.
    assert compressed[-2:] == messages[-2:]
    assert compressed[3]["content"].startswith("a" * 100)
    assert "compressed 4900 chars" in compressed[3]["content"]
    assert serialized_conversation_bytes(compressed, ChildAgent.tools()) <= 8000

    # A history within budget is returned verbatim.
    small = messages[:1] + messages[-2:]
    assert ChildAgent._compress_messages(
        small, context_budget_chars=100_000, keep_recent=8,
        max_old_tool_content_chars=100,
    ) is small
