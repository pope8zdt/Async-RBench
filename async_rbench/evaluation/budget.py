"""Token budget pools and ledger (spec §7).

Each pool is an independent, separately-locked token account with strict
conservative admission: a call may start only if
``estimated_input_upper_bound + requested_max_output <= remaining``.  Pools do
not borrow from one another, so a child's usage can never consume ``main_post``
budget.  Settling records the provider's true token usage; an actual total above
the reservation yields ``budget_overrun`` and halts that pool's subsequent
admissions.

This module is transport/driver free: it knows nothing about the model backend
or the protocol emitter.  The reference scaffold wires the ledger to the backend
estimator and emits budget events; the pool merely carries the accounting
state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class Reservation:
    """One admitted call's provisional charge against a pool.

    ``estimated_total`` is the conservative admission bound (``input_upper_bound +
    max_output``).  The caller settles to the provider's true usage after the call
    returns; any excess is recorded as overrun on the pool.
    """

    reservation_id: str
    pool_name: str
    input_upper_bound: int
    max_output: int
    accounting_mode: str
    settled: bool = False
    actual_total: int | None = None

    @property
    def estimated_total(self) -> int:
        return self.input_upper_bound + self.max_output


class BudgetPool:
    """An independently locked, independently settled token account.

    ``remaining`` is the room still available for new admissions
    (``maximum - reserved - settled``).  A settle whose actual usage exceeds the
    reservation records ``overrun`` and halts the pool: subsequent admissions are
    refused so a single too-conservative estimate cannot silently push past the
    cap (spec §7.3).
    """

    def __init__(
        self,
        name: str,
        maximum: int,
        *,
        reserved: int = 0,
        settled: int = 0,
        overrun: int = 0,
        accounting_mode: str = "provider_exact",
    ) -> None:
        self.name = name
        self.maximum = maximum
        self.reserved = reserved
        self.settled = settled
        self.overrun = overrun
        self.accounting_mode = accounting_mode
        self.halted = False
        self._lock = asyncio.Lock()
        self._reservations: dict[str, Reservation] = {}
        self._sequence = 0

    @property
    def remaining(self) -> int:
        if self.halted:
            return 0
        return max(0, self.maximum - self.reserved - self.settled)

    @property
    def snapshot(self) -> dict[str, Any]:
        return {
            "pool": self.name,
            "maximum": self.maximum,
            "reserved": self.reserved,
            "settled": self.settled,
            "remaining": self.remaining,
            "overrun": self.overrun,
            "accounting_mode": self.accounting_mode,
            "halted": self.halted,
        }

    async def reserve(
        self,
        input_upper_bound: int,
        max_output: int,
        *,
        accounting_mode: str = "provider_exact",
    ) -> Reservation | None:
        """Admit one call under strict conservative admission, or return None.

        The call starts only if ``input_upper_bound + max_output`` still fits in
        the pool remaining.  Returns a :class:`Reservation` on success and
        ``None`` when the pool is halted or the admission would overrun.
        """
        input_upper_bound = max(0, int(input_upper_bound))
        max_output = max(0, int(max_output))
        estimate = input_upper_bound + max_output
        async with self._lock:
            if self.halted:
                return None
            if self.reserved + self.settled + estimate > self.maximum:
                return None
            self._sequence += 1
            reservation = Reservation(
                reservation_id=f"{self.name}#r{self._sequence}",
                pool_name=self.name,
                input_upper_bound=input_upper_bound,
                max_output=max_output,
                accounting_mode=accounting_mode,
            )
            self._reservations[reservation.reservation_id] = reservation
            self.reserved += estimate
            if accounting_mode == "conservative":
                self.accounting_mode = "conservative"
            return reservation

    async def settle(self, reservation_id: str, actual_total_tokens: int) -> int:
        """Settle one reservation to the provider's true usage; return overrun.

        Idempotence: a second settle of the same reservation id raises, as does a
        settle for an unknown id.  An actual total above the reservation estimate
        is recorded as overrun and halts the pool's future admissions.
        """
        actual_total_tokens = max(0, int(actual_total_tokens))
        async with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise ValueError(f"unknown reservation {reservation_id!r}")
            if reservation.settled:
                raise ValueError(f"reservation {reservation_id!r} is already settled")
            self.reserved -= reservation.estimated_total
            overrun = max(0, actual_total_tokens - reservation.estimated_total)
            if overrun > 0:
                self.overrun += overrun
                self.halted = True
            self.settled += actual_total_tokens
            reservation.settled = True
            reservation.actual_total = actual_total_tokens
            return overrun


class BudgetLedger:
    """Per-mode pool routing.

    * ``child`` -> ``child_shared`` in every mode.
    * ``main`` in ``linear`` -> the single ``main_total`` pool.
    * ``main`` in ``async`` -> ``main_pre`` until the first scored presentation,
      then ``main_post`` (spec §7.1).  The switch is explicit via
      :meth:`switch_to_post`; the caller decides when the phase boundary is met.
    """

    def __init__(self, *, mode: str, pools: dict[str, BudgetPool]) -> None:
        self.mode = mode
        self.pools = pools
        self._main_phase = "pre"

    def pool(self, name: str) -> BudgetPool:
        return self.pools[name]

    @property
    def main_phase(self) -> str:
        return self._main_phase

    def for_role(self, role: str, phase: str | None = None) -> BudgetPool:
        if role == "child":
            return self.pools["child_shared"]
        if self.mode == "linear":
            return self.pools["main_total"]
        return self.pools[f"main_{phase or self._main_phase}"]

    def main_pool(self) -> BudgetPool:
        return self.for_role("main", self._main_phase)

    def switch_to_post(self) -> None:
        self._main_phase = "post"

    def all_snapshots(self) -> dict[str, dict[str, Any]]:
        return {name: pool.snapshot for name, pool in self.pools.items()}


def build_budget_ledger(
    mode: str,
    *,
    child_shared: int,
    main_pre: int,
    main_post: int,
    main_total: int,
) -> BudgetLedger:
    """Build the four named pools and route them for ``mode`` (async/linear)."""
    pools = {
        "child_shared": BudgetPool("child_shared", child_shared),
        "main_pre": BudgetPool("main_pre", main_pre),
        "main_post": BudgetPool("main_post", main_post),
        "main_total": BudgetPool("main_total", main_total),
    }
    return BudgetLedger(mode=mode, pools=pools)
