from __future__ import annotations

import asyncio

import pytest

from async_rbench.evaluation.token_usage import TokenUsageLedger


def test_actual_usage_is_counted_by_role_and_actor() -> None:
    async def exercise() -> dict[str, object]:
        ledger = TokenUsageLedger(emergency_cap=100)
        await ledger.record("main", 11)
        await ledger.record("child:c1", 7)
        await ledger.record("child:c2", 5)
        return ledger.snapshot

    assert asyncio.run(exercise()) == {
        "emergency_cap": 100,
        "total": 23,
        "main": 11,
        "child": 12,
        "by_actor": {"child:c1": 7, "child:c2": 5, "main": 11},
        "tripped": False,
        "trigger_role": None,
    }


def test_emergency_crossing_is_reported_once_and_late_settlements_are_counted() -> None:
    async def exercise() -> tuple[object, object, object, bool, dict[str, object]]:
        ledger = TokenUsageLedger(emergency_cap=10)
        first = await ledger.record("child:c1", 6)
        crossing = await ledger.record("main", 4)
        late = await ledger.record("child:c2", 3)
        return first, crossing, late, await ledger.can_start(), ledger.snapshot

    first, crossing, late, can_start, snapshot = asyncio.run(exercise())
    assert first.crossed_now is False
    assert first.tripped is False
    assert crossing.crossed_now is True
    assert crossing.tripped is True
    assert crossing.total == 10
    assert late.crossed_now is False
    assert late.tripped is True
    assert late.total == 13
    assert can_start is False
    assert snapshot["total"] == 13
    assert snapshot["trigger_role"] == "main"


def test_concurrent_actual_usage_updates_are_atomic() -> None:
    async def exercise() -> dict[str, object]:
        ledger = TokenUsageLedger(emergency_cap=10_000)
        await asyncio.gather(*(
            ledger.record(f"child:c{index % 3}", 2)
            for index in range(100)
        ))
        return ledger.snapshot

    snapshot = asyncio.run(exercise())
    assert snapshot["total"] == 200
    assert snapshot["child"] == 200
    assert sum(snapshot["by_actor"].values()) == 200


def test_negative_usage_is_normalized_and_cap_must_be_positive() -> None:
    async def exercise() -> dict[str, object]:
        ledger = TokenUsageLedger(emergency_cap=10)
        await ledger.record("main", -7)
        return ledger.snapshot

    assert asyncio.run(exercise())["total"] == 0
    with pytest.raises(ValueError, match="emergency_cap must be positive"):
        TokenUsageLedger(emergency_cap=0)
