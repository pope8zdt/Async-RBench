from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

import pytest

from async_rbench.evaluation.budget import BudgetLedger, BudgetPool, build_budget_ledger
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import ChildRecord, ReferenceScaffold
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
        delivery_reader=DeliveryReader(),
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
