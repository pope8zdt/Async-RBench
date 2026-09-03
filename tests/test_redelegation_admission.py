from __future__ import annotations

"""Task 7: exact re-delegation admission and bounded recovery.

The recovery admission path must (a) reserve the exact conservative estimate of
the recovery child's real first model call at spawn time, atomically, instead of
gating on a crude ``2 * max_output_tokens`` floor, and (b) enforce a hard
per-workstream recovery cap that is independent of whether the free-text
evidence digest changed between attempts.

Covers the five Task 7 acceptance behaviours:

1. Pool remaining > ``2 * max_output_tokens`` but < the real first-call cost is
   refused.
2. A pool halted by an estimation overrun refuses the spawn as an infrastructure
   accounting failure, never as an insufficient participant budget.
3. Two concurrent recovery spawns competing for one call of remaining budget
   admit exactly one (reservation is atomic).
4. One initial attempt plus one recovery is allowed; a second recovery for the
   same workstream is refused even if the evidence digest changes.
5. The previous rejection feedback is still present in the accepted recovery
   child's initial prompt.
"""

import asyncio
import io
import json
import sys
from pathlib import Path

import yaml

from async_rbench.evaluation.model_backend import conservative_input_estimate
from async_rbench.evaluation.runner import EpisodeConfig, _make_start
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import (
    ChildAgent, ChildRecord, ReferenceScaffold, compress_child_messages,
)
from async_rbench.spec import load_case

ROOT = Path(__file__).resolve().parents[1]

WAL_TASK = "retry wal recovery with a complete report artifact"
CHECK_TASK = "retry checkpoint recovery with a complete report artifact"


def _start() -> dict:
    case_path = ROOT / "cases" / "data-recovery-service" / "public_case.yaml"
    case = load_case(case_path).raw
    task = yaml.safe_load((case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8"))
    config = EpisodeConfig(
        episode_id="test-episode", case_id="data-recovery-service", execution_mode="linear",
        guidance="incentive", agent_seed=1, adapter_command=[sys.executable],
        output_dir=ROOT / "artifacts" / "test-unused", use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _build_manager(max_output_tokens: int = 8192) -> ReferenceScaffold:
    """A scaffold whose three initial workstreams are assigned and whose
    ``wal_recovery`` / ``checkpoint_recovery`` initial children carry an
    actionable rejection (so a recovery spawn for them reaches admission)."""
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "workspace_mode": "disabled",
        "max_output_tokens": max_output_tokens,
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
    for index, (child_id, workstream_id) in enumerate([
        ("c-wal", "wal_recovery"),
        ("c-check", "checkpoint_recovery"),
        ("c-merge", "merge_support"),
    ]):
        record = ChildRecord(
            child_id=child_id, task="t", work_units=[workstream_id], targets=[],
            expected_output="e", priority="normal", status="completed_hidden",
            completion_id=f"comp-{child_id}",
        )
        manager.children[child_id] = record
        manager.completion_to_child[f"comp-{child_id}"] = child_id
    # The benchmark-owned initial wave counts one attempt per workstream before
    # any child could be rejected (as a real spawn_initial_wave would).
    manager.attempt_counts["wal_recovery"] = 1
    manager.attempt_counts["checkpoint_recovery"] = 1
    manager._launch_queued = lambda: None  # keep the recovery children un-run
    return scaffold


async def _reject(manager, child_id: str, workstream_id: str, code: str) -> None:
    """Route an actionable gateway rejection for one registered initial child."""
    await manager.handle_rejection({
        "completion_id": f"comp-{child_id}",
        "reason_codes": [code], "child_id": child_id,
    })
    assert manager.workstream_rejections[workstream_id]["actionable"] is True


def _registered_child_count(manager) -> int:
    return len(manager.children)


def _messages_for(record: ChildRecord) -> list[dict]:
    return ChildAgent.initial_messages(record)


# --- Acceptance 1: the crude 2*max_output floor no longer admits a spawn whose
# --- real first call would not fit in the remaining pool. --------------------


def test_recovery_refused_when_pool_holds_two_max_output_but_not_the_exact_call() -> None:
    async def exercise() -> None:
        scaffold = _build_manager(max_output_tokens=64)
        manager = scaffold.manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")
        pool = manager.token_budget
        # Remaining is far above the old 2 * max_output floor (128) yet well
        # below the conservative serialized first-call estimate (kilotokens).
        pool.settled += pool.maximum - 700
        assert pool.remaining == 700
        assert pool.remaining >= 2 * manager.config.max_output_tokens

        before = _registered_child_count(manager)
        result = await manager.spawn("wal_recovery", WAL_TASK, [], "", "high")

        assert "error" in result, "spawn must be refused once the exact first call no longer fits"
        assert "exact first call" in result["error"]
        assert result["budget_consumed"] is False
        assert pool.refusal_reason == "insufficient_remaining"
        assert _registered_child_count(manager) == before
        assert pool.reserved == 0  # the refused admission consumed nothing

    asyncio.run(exercise())


# --- Acceptance 2: a pool halted by an estimation overrun is an infrastructure
# --- accounting failure, not an insufficient participant budget. -------------


def test_recovery_refused_as_infrastructure_accounting_when_pool_halted() -> None:
    async def exercise() -> None:
        scaffold = _build_manager()
        manager = scaffold.manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")
        pool = manager.token_budget
        pool.halted = True
        pool.halt_reason = "estimation_overrun"
        pool.overrun = 1000

        before = _registered_child_count(manager)
        result = await manager.spawn("wal_recovery", WAL_TASK, [], "", "high")

        assert "error" in result
        assert "halted" in result["error"]
        assert "infrastructure accounting failure" in result["error"]
        # It must NOT be classified as the model simply exhausting its budget.
        assert "insufficient participant budget" not in result["error"]
        assert "exact first call" not in result["error"]
        assert pool.refusal_reason == "halted_pool"
        assert result["budget_consumed"] is False
        assert _registered_child_count(manager) == before

    asyncio.run(exercise())


# --- Acceptance 3: two concurrent recovery spawns racing for one call of
# --- remaining budget admit exactly one (the reservation is atomic). ---------


def test_concurrent_recovery_spawns_race_for_one_call_of_remaining_budget() -> None:
    async def exercise() -> None:
        # Measure the real first-call cost of a wal and a checkpoint recovery on
        # a throwaway manager built from the identical start/config.
        probe = _build_manager()
        await _reject(probe.manager, "c-wal", "wal_recovery", "report_file_missing")
        await _reject(probe.manager, "c-check", "checkpoint_recovery", "report_file_missing")
        wal_result = await probe.manager.spawn("wal_recovery", WAL_TASK, [], "", "high")
        check_result = await probe.manager.spawn("checkpoint_recovery", CHECK_TASK, [], "", "high")
        assert "child_id" in wal_result and "child_id" in check_result
        one_call_wal = probe.manager.children[wal_result["child_id"]].initial_reservation.estimated_total
        one_call_check = probe.manager.children[check_result["child_id"]].initial_reservation.estimated_total
        one_call = max(one_call_wal, one_call_check)

        # A fresh manager whose child pool has exactly one recovery call left.
        manager = _build_manager().manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")
        await _reject(manager, "c-check", "checkpoint_recovery", "report_file_missing")
        manager.token_budget.maximum = one_call
        assert manager.token_budget.remaining == one_call

        results = await asyncio.gather(
            manager.spawn("wal_recovery", WAL_TASK, [], "", "high"),
            manager.spawn("checkpoint_recovery", CHECK_TASK, [], "", "high"),
        )
        successes = [result for result in results if "child_id" in result]
        refusals = [result for result in results if "error" in result]
        assert len(successes) == 1, f"exactly one concurrent recovery spawn must win: {results}"
        assert len(refusals) == 1
        assert "exact first call" in refusals[0]["error"]
        assert manager.token_budget.refusal_reason == "insufficient_remaining"
        # 3 benchmark-owned initial children + exactly one admitted recovery.
        assert _registered_child_count(manager) == 4
        admitted = successes[0]["child_id"]
        assert manager.children[admitted].initial_reservation is not None
        # The winning reservation is held against the pool (budget committed).
        assert manager.token_budget.reserved == one_call_wal or manager.token_budget.reserved == one_call_check

    asyncio.run(exercise())


# --- Acceptance 4: one initial attempt + one recovery is allowed; a second
# --- recovery for the same workstream is refused by the hard per-workstream cap
# --- even when the free-text evidence digest has changed. --------------------


def test_second_recovery_for_workstream_refused_even_when_evidence_digest_changes() -> None:
    async def exercise() -> None:
        scaffold = _build_manager()
        manager = scaffold.manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")

        first = await manager.spawn("wal_recovery", WAL_TASK, [], "", "high")
        assert "child_id" in first, "initial attempt + one recovery must be allowed"
        assert manager.recovery_spawn_counts["wal_recovery"] == 1
        assert len(manager.children) == 4

        before = _registered_child_count(manager)
        # Even if the next attempt would carry brand-new free-text evidence (a
        # digest the runtime has never seen), the per-workstream recovery cap
        # still refuses it: changed digest is not proof of new information.
        manager.workstream_evidence_digests["wal_recovery"].append("brand-new-digest")
        second = await manager.spawn("wal_recovery", WAL_TASK + " v2", [], "", "high")
        assert "error" in second
        assert "maximum recovery attempts for workstream" in second["error"]
        assert second["budget_consumed"] is False
        assert _registered_child_count(manager) == before
        assert manager.recovery_spawn_counts["wal_recovery"] == 1

    asyncio.run(exercise())


# --- Acceptance 5: the accepted recovery child still carries the previous
# --- rejection feedback in the exact first prompt it was admitted for, and the
# --- first-call reservation is held against the pool while it is queued. ------


def test_accepted_recovery_prompt_keeps_prior_rejection_feedback_and_reserved_call() -> None:
    async def exercise() -> None:
        scaffold = _build_manager()
        manager = scaffold.manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")
        pool = manager.token_budget
        remaining_before = pool.remaining

        result = await manager.spawn("wal_recovery", WAL_TASK, [], "", "high")
        assert "child_id" in result
        record = manager.children[result["child_id"]]
        assert record.attempt_number == 2
        assert record.prior_attempt_rejection["reason_codes"] == ["report_file_missing"]
        assert record.initial_reservation is not None

        # The budget is committed while the recovery child is queued: the stored
        # reservation is exactly the reserved first call.
        assert pool.remaining == remaining_before - record.initial_reservation.estimated_total

        # The prompt the child would send on turn one still carries the feedback.
        messages = _messages_for(record)
        user_payload = json.loads(messages[1]["content"])
        assert user_payload["prior_attempt"] == {
            "failed_attempt_count": 1,
            "last_rejection": {
                "reason_codes": ["report_file_missing"],
                "contract_part": "report_file",
            },
        }
        # Admission was based on the exact serialized first call (compress then
        # conservative estimate), so the reserved input bound is that estimate.
        tools = ChildAgent.tools()
        compressed = compress_child_messages(
            messages, tools,
            budget_bytes=scaffold.config.child_context_budget_bytes,
            keep_recent_blocks=scaffold.config.child_keep_recent_turns,
            excerpt_chars=scaffold.config.child_old_tool_excerpt_chars,
        )
        assert conservative_input_estimate(compressed, tools) == record.initial_reservation.input_upper_bound

    asyncio.run(exercise())


def test_initial_reservation_field_defaults_to_none_on_benchmark_owned_children() -> None:
    """The new field is a recovery-only affordance; benchmark-owned children must
    not accidentally carry one (keeps the Linear/Async records comparable)."""
    async def exercise() -> None:
        scaffold = _build_manager()
        # _build_manager registered three assigned children; start a clean wave
        # on a fresh manager instead.
        fresh = ReferenceScaffold(
            start=_start(),
            config=scaffold.config,
            backend=ScriptedTestBackend(),
            workspace=DisabledWorkspaceRuntime(),
            emitter=ProtocolEmitter(stdout=io.StringIO()),
            delivery_reader=DeliveryReader(stdin=io.StringIO()),
        )
        fresh.manager._launch_queued = lambda: None
        result = fresh.manager.spawn_initial_wave()
        assert "error" not in result
        assert len(fresh.manager.children) == 3
        for record in fresh.manager.children.values():
            assert record.initial_wave is True
            assert record.initial_reservation is None

    asyncio.run(exercise())


def test_recovery_child_run_consumes_the_stored_first_call_reservation() -> None:
    """The reservation ``spawn`` commits at admission is consumed by the child's
    real first model turn: ``ChildAgent.run`` settles exactly that reservation
    (one ``budget_reserved`` at spawn + one ``budget_settled`` for the same id)
    instead of reserving a second time, and clears the stored field."""
    async def exercise() -> None:
        scaffold = _build_manager()
        manager = scaffold.manager
        await _reject(manager, "c-wal", "wal_recovery", "report_file_missing")

        result = await manager.spawn("wal_recovery", WAL_TASK, [], "", "high")
        assert "child_id" in result
        record = manager.children[result["child_id"]]
        reservation = record.initial_reservation
        assert reservation is not None
        pool = manager.token_budget
        # The exact first call is committed against the pool while queued.
        assert pool.reserved == reservation.estimated_total

        # Drive the child's own first model call (the path ``_run_child`` takes
        # for an admitted recovery child) without the queue launch.
        agent = ChildAgent(
            manager.backend, manager.workspace, manager.config, manager.emitter,
            pool,
        )
        await agent.run(
            record, manager.config.child_model,
            int(scaffold.start["agent_seed"]),
        )

        # Turn 1 consumed the stored reservation (no second reserve) and settled
        # it against the pool; nothing is left reserved.
        assert record.initial_reservation is None
        assert reservation.settled is True
        assert pool.reserved == 0
        events = [
            event for event in scaffold.emitter.events
            if event.get("reservation_id") == reservation.reservation_id
        ]
        assert [(event["type"]) for event in events] == [
            "budget_reserved", "budget_settled",
        ]

    asyncio.run(exercise())
