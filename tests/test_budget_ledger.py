from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

import pytest

from async_rbench.evaluation.budget import BudgetLedger, BudgetPool, build_budget_ledger
from async_rbench.evaluation.case_contract import public_rejection
from async_rbench.evaluation.event_store import strip_for_adapter
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import (
    ChildAgent, ChildRecord, ReferenceScaffold,
)
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


def _start(case_id: str = "data-recovery-service", mode: str = "async") -> dict:
    case_path = ROOT / "cases" / case_id / "public_case.yaml"
    case = load_case(case_path).raw
    import yaml

    task = yaml.safe_load((case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8"))
    from async_rbench.evaluation.runner import EpisodeConfig, _make_start

    config = EpisodeConfig(
        episode_id="budget-episode", case_id=case_id, execution_mode=mode,
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
        # An empty stdin lets a started DeliveryReader hit EOF and exit cleanly
        # instead of reading pytest's captured stdin (which raises an OSError).
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
    )


def _inject_delivery(scaffold: ReferenceScaffold, child_id: str, completion_id: str) -> None:
    scaffold.manager.children[child_id] = ChildRecord(
        child_id=child_id, task="work", work_units=["wal_recovery"], targets=[],
        expected_output="out", priority="high", status="completed_hidden",
        completion_id=completion_id,
    )
    scaffold.manager.completion_to_child[completion_id] = child_id


# --- Step 1: pool isolation, no borrowing, atomic concurrency ---------------


def test_child_usage_does_not_consume_main_post_budget() -> None:
    async def exercise() -> tuple[int, int]:
        ledger = build_budget_ledger(
            "async", child_shared=1_000_000, main_pre=500_000,
            main_post=500_000, main_total=1_000_000,
        )
        child = ledger.pool("child_shared")
        reservation = await child.reserve(0, 1_000_000)
        assert reservation is not None
        await child.settle(reservation.reservation_id, 1_000_000)
        # child consumed its full 1M; main_post is independently untouched.
        return child.remaining, ledger.pool("main_post").remaining

    assert asyncio.run(exercise()) == (0, 500_000)


def test_ledger_pools_never_borrow() -> None:
    async def exercise() -> None:
        ledger = build_budget_ledger(
            "async", child_shared=1_000_000, main_pre=500_000,
            main_post=500_000, main_total=1_000_000,
        )
        main_pre = ledger.pool("main_pre")
        first = await main_pre.reserve(400_000, 0)
        assert first is not None
        # Sweeping main_pre does not reduce child_shared or main_post room.
        assert ledger.pool("child_shared").remaining == 1_000_000
        assert ledger.pool("main_post").remaining == 500_000
        # main_pre cannot borrow from a sibling even though they still have room.
        assert await main_pre.reserve(200_000, 0) is None

    asyncio.run(exercise())


def test_linear_uses_single_main_total_pool() -> None:
    async def exercise() -> None:
        ledger = build_budget_ledger(
            "linear", child_shared=1_000_000, main_pre=500_000,
            main_post=500_000, main_total=1_000_000,
        )
        assert ledger.for_role("main") is ledger.pool("main_total")
        assert ledger.for_role("child") is ledger.pool("child_shared")
        # The two 500k main pools are merged into one 1M main_total pool.
        assert ledger.pool("main_total").maximum == 1_000_000

    asyncio.run(exercise())


def test_concurrent_child_reservations_are_atomic() -> None:
    async def exercise() -> tuple[int, int]:
        ledger = build_budget_ledger(
            "async", child_shared=1_000_000, main_pre=500_000,
            main_post=500_000, main_total=1_000_000,
        )
        child = ledger.pool("child_shared")

        async def attempt() -> object | None:
            return await child.reserve(100_000, 0)

        results = await asyncio.gather(*[attempt() for _ in range(20)])
        admitted = [r for r in results if r is not None]
        # Exactly 1M // 100k reservations fit atomically, never more.
        return len(admitted), child.reserved

    assert asyncio.run(exercise()) == (10, 1_000_000)


# --- Fix #1: failed calls release their reservation (no leak into ``reserved``) -


def test_release_returns_provisional_charge_to_pool() -> None:
    async def exercise() -> None:
        pool = BudgetPool("child_shared", 1_000_000)
        reservation = await pool.reserve(100, 200)
        assert reservation is not None
        assert pool.reserved == 300
        assert reservation.released is False
        await pool.release(reservation.reservation_id)
        assert reservation.released is True
        assert pool.reserved == 0
        assert pool.remaining == 1_000_000
        # A released reservation frees the room, so a later call fits again.
        assert await pool.reserve(100, 200) is not None

    asyncio.run(exercise())


def test_release_marks_reservation_released_and_blocks_settle() -> None:
    async def exercise() -> None:
        pool = BudgetPool("child_shared", 1_000_000)
        reservation = await pool.reserve(10, 20)
        assert reservation is not None
        await pool.release(reservation.reservation_id)
        # Settling after a release is an error (guards against double bookkeeping).
        with pytest.raises(ValueError):
            await pool.settle(reservation.reservation_id, 30)

    asyncio.run(exercise())


def test_release_rejects_unknown_duplicate_and_settled() -> None:
    async def exercise() -> None:
        pool = BudgetPool("child_shared", 1_000_000)
        with pytest.raises(ValueError):
            await pool.release("no-such-reservation")
        reservation = await pool.reserve(10, 20)
        await pool.release(reservation.reservation_id)
        with pytest.raises(ValueError):
            await pool.release(reservation.reservation_id)
        other = await pool.reserve(10, 20)
        assert other is not None
        await pool.settle(other.reservation_id, 30)
        with pytest.raises(ValueError):
            await pool.release(other.reservation_id)

    asyncio.run(exercise())


def test_child_agent_releases_open_reservation_on_failure_path() -> None:
    async def exercise() -> None:
        pool = BudgetPool("child_shared", 1_000_000)
        agent = ChildAgent(
            backend=ScriptedTestBackend(),
            workspace=DisabledWorkspaceRuntime(),
            config=_scaffold(_start()).config,
            emitter=ProtocolEmitter(stdout=io.StringIO()),
            token_budget=pool,
        )
        reservation = await pool.reserve(100, 200)
        assert reservation is not None
        agent._open_reservation = reservation
        # A child timeout / backend raise runs this before the task is dropped.
        await agent.release_open_reservation()
        assert pool.reserved == 0
        assert agent._open_reservation is None
        # Releasing twice is a no-op (the second call finds nothing open).
        await agent.release_open_reservation()

    asyncio.run(exercise())


def test_main_loop_releases_reservation_when_backend_raises() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "async"))
        main_pre = scaffold.budget_ledger.pool("main_pre")

        async def boom(*args, **kwargs):
            raise RuntimeError("simulated provider outage")

        scaffold.backend.complete = boom
        await scaffold.run()
        await scaffold.shutdown()
        # The failed main call released its provisional charge, so the pool is
        # not left with a stuck reservation; the episode is an infrastructure
        # failure, not a budget one.
        assert main_pre.reserved == 0
        assert scaffold.finish_status == "incomplete"

    asyncio.run(exercise())


# --- Fix #7: main loop reserves/settles from the correct phase pool ----------


def test_main_loop_reserves_and_settles_from_correct_phase_pool() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "async"))
        ledger = scaffold.budget_ledger
        # Pre-phase: the main loop reserves from main_pre.
        assert ledger.main_pool() is ledger.pool("main_pre")
        reservation = await ledger.main_pool().reserve(
            100, 200, accounting_mode="conservative",
        )
        assert reservation is not None
        await ledger.pool("main_pre").settle(reservation.reservation_id, 250)
        assert ledger.pool("main_pre").settled == 250
        assert ledger.pool("main_pre").remaining == 500_000 - 250

        # A scored presentation flips the loop onto main_post for later calls.
        _inject_delivery(scaffold, "c1", "comp-1")
        await scaffold.manager.handle_delivery(
            {"completion_id": "comp-1", "payload": {"id": 1}},
        )
        candidate = scaffold.manager.select_presentable()
        assert candidate is not None and candidate.scored is True
        scaffold.manager.mark_presented(
            candidate.occurrence_id, turn_id="t1", window_id="w1",
        )
        scaffold._on_result_presented(candidate.occurrence_id)
        assert ledger.main_pool() is ledger.pool("main_post")
        reservation2 = await ledger.pool("main_post").reserve(
            50, 100, accounting_mode="conservative",
        )
        assert reservation2 is not None
        await ledger.pool("main_post").settle(reservation2.reservation_id, 120)
        assert ledger.pool("main_post").remaining == 500_000 - 120

    asyncio.run(exercise())


def test_linear_main_loop_uses_single_main_total_pool() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "linear"))
        ledger = scaffold.budget_ledger
        assert ledger.main_pool() is ledger.pool("main_total")
        reservation = await ledger.main_pool().reserve(
            10, 20, accounting_mode="conservative",
        )
        assert reservation is not None
        await ledger.pool("main_total").settle(reservation.reservation_id, 30)
        assert ledger.pool("main_total").remaining == 1_000_000 - 30

    asyncio.run(exercise())


def test_main_loop_budget_exhausted_when_main_reserve_refused() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "async"))
        # Force every main admission to be refused so the loop's first main
        # reserve returns None, which must set finish_status=budget_exhausted and
        # return from run().
        scaffold.budget_ledger.pool("main_pre").maximum = 0
        await scaffold.run()
        await scaffold.shutdown()
        assert scaffold.finish_status == "budget_exhausted"
        assert scaffold.final_summary == "episode token budget exhausted"

    asyncio.run(exercise())


def test_async_phase_switch_on_first_scored_result_presented() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "async"))
        ledger = scaffold.budget_ledger
        assert ledger.main_phase == "pre"
        assert ledger.main_pool() is ledger.pool("main_pre")

        _inject_delivery(scaffold, "c1", "comp-1")
        await scaffold.manager.handle_delivery(
            {"completion_id": "comp-1", "payload": {"id": 1}},
        )
        candidate = scaffold.manager.select_presentable()
        assert candidate is not None
        assert candidate.scored is True
        scaffold.manager.mark_presented(
            candidate.occurrence_id, turn_id="t1", window_id="w1",
        )
        scaffold._on_result_presented(candidate.occurrence_id)

        assert ledger.main_phase == "post"
        assert ledger.main_pool() is ledger.pool("main_post")

    asyncio.run(exercise())


def test_non_scored_presentation_does_not_switch_phase() -> None:
    async def exercise() -> None:
        scaffold = _scaffold(_start("data-recovery-service", "async"))
        ledger = scaffold.budget_ledger
        # A non-scored (plan_formation_input) occurrence must NOT switch phase.
        from async_rbench.evaluation.presentation import DeliveryOccurrence

        occurrence = DeliveryOccurrence(
            occurrence_id="occ-nonscored",
            completion_id="comp-nonscored",
            payload={"id": 1},
            receive_seq=1,
            scored=False,
        )
        scaffold.manager.presentation_queue.enqueue(occurrence)
        candidate = scaffold.manager.select_presentable()
        assert candidate is not None and candidate.scored is False
        scaffold.manager.mark_presented(
            candidate.occurrence_id, turn_id="t1", window_id="w1",
        )
        scaffold._on_result_presented(candidate.occurrence_id)

        assert ledger.main_phase == "pre"

    asyncio.run(exercise())


# --- Step 2: overrun halts the pool ----------------------------------------


def test_budget_overrun_records_overrun_and_stops_pool() -> None:
    async def exercise() -> None:
        pool = BudgetPool("main_post", 1000)
        reservation = await pool.reserve(10, 20)  # estimate = 30
        assert reservation is not None
        overrun = await pool.settle(reservation.reservation_id, 35)
        assert overrun == 5
        assert pool.overrun == 5
        assert pool.halted is True
        assert pool.remaining == 0
        # The pool refuses any subsequent admission after an overrun.
        assert await pool.reserve(1, 1) is None

    asyncio.run(exercise())


def test_refusal_reason_distinguishes_halt_from_insufficient_remaining() -> None:
    """Two termination causes must never be conflated: the pool halting after an
    estimation overrun (a benchmark defect) vs a genuine admission shortfall
    (the model consumed its bounded budget)."""
    async def exercise() -> None:
        # Genuine shortfall: the admission does not fit the remaining balance.
        # The pool is NOT halted; the refusal is an admission refusal.
        exhausted = BudgetPool("main_pre", 1000)
        assert await exhausted.reserve(800, 200) is not None
        assert exhausted.refusal_reason is None
        assert await exhausted.reserve(10, 20) is None
        assert exhausted.refusal_reason == "insufficient_remaining"
        assert exhausted.halted is False
        assert exhausted.halt_reason is None

        # Estimation-error halt: a settled call exceeds its reservation.
        halted = BudgetPool("main_pre", 1000)
        reservation = await halted.reserve(10, 20)
        assert reservation is not None
        await halted.settle(reservation.reservation_id, 1_000_000)
        assert halted.halted is True
        assert halted.halt_reason == "estimation_overrun"
        # After the halt, a future admission is refused as ``halted_pool`` --
        # distinct from the "insufficient_remaining" refusal above.
        assert await halted.reserve(1, 1) is None
        assert halted.refusal_reason == "halted_pool"
        # Snapshot carries both causes for the per-pool report.
        snapshot = halted.snapshot
        assert snapshot["halt_reason"] == "estimation_overrun"
        assert snapshot["refusal_reason"] == "halted_pool"
        assert snapshot["remaining"] == 0

    asyncio.run(exercise())


def test_settle_rejects_unknown_and_duplicate_reservation() -> None:
    async def exercise() -> None:
        pool = BudgetPool("child_shared", 1_000_000)
        with pytest.raises(ValueError):
            await pool.settle("no-such-reservation", 10)
        reservation = await pool.reserve(10, 20)
        await pool.settle(reservation.reservation_id, 30)
        with pytest.raises(ValueError):
            await pool.settle(reservation.reservation_id, 31)

    asyncio.run(exercise())


# --- P0-6: rejection projection must preserve the already-public workstream_id
# when strip_for_adapter re-projects an event that carries it -----------------


def test_public_rejection_preserves_workstream_id_from_event() -> None:
    # _record_gateway_outcome stamps workstream_id onto the event; strip_for_adapter
    # re-projects it WITHOUT the keyword, so the projection must fall back to the
    # event field instead of nulling it.
    rejection = {
        "type": "result_rejected", "child_id": "c1", "completion_id": "comp-1",
        "workstream_id": "requirement_worker_01",
        "reason_codes": ["missing_required_files"],
    }
    plain = public_rejection(rejection)
    assert plain["workstream_id"] == "requirement_worker_01"
    # strip_for_adapter is the adapter-facing projection and must keep it too.
    stripped = strip_for_adapter(rejection)
    assert stripped["type"] == "result_rejected"
    assert stripped["workstream_id"] == "requirement_worker_01"


def test_strict_admission_is_input_upper_bound_plus_max_output() -> None:
    async def exercise() -> None:
        # maximum chosen so the two admissions exactly fill it, and a third
        # reservation over the remaining (by a single token) is refused.
        pool = BudgetPool("main_pre", 1031)
        assert await pool.reserve(10, 20) is not None      # 30
        assert await pool.reserve(30, 970) is not None      # 1000
        assert pool.remaining == 1
        # Strict admission: input_upper_bound + requested_max_output <= remaining.
        assert await pool.reserve(1, 1) is None             # 2 > 1

    asyncio.run(exercise())
