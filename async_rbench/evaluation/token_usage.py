"""Actual token-use accounting and the episode emergency safety fuse."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenUsageUpdate:
    """Result of settling one completed provider call."""

    total: int
    tripped: bool
    crossed_now: bool


class TokenUsageLedger:
    """Count actual provider usage without gating ordinary model calls.

    The only limit is a deliberately high episode-wide emergency fuse. Calls
    already in flight still settle after it trips, so the final diagnostic is a
    complete account of provider-reported use rather than an admission estimate.
    """

    def __init__(self, *, emergency_cap: int) -> None:
        if int(emergency_cap) <= 0:
            raise ValueError("emergency_cap must be positive")
        self.emergency_cap = int(emergency_cap)
        self.total = 0
        self.main = 0
        self.child = 0
        self.by_actor: defaultdict[str, int] = defaultdict(int)
        self.tripped = False
        self.trigger_role: str | None = None
        self._lock = asyncio.Lock()

    async def can_start(self) -> bool:
        """Return whether the emergency fuse still permits a new model call."""
        async with self._lock:
            return not self.tripped

    async def record(self, role: str, actual_tokens: int) -> TokenUsageUpdate:
        """Atomically add one completed call's actual token use."""
        actual = max(0, int(actual_tokens))
        actor = str(role)
        async with self._lock:
            self.total += actual
            self.by_actor[actor] += actual
            if actor == "main":
                self.main += actual
            elif actor.startswith("child:"):
                self.child += actual
            crossed_now = not self.tripped and self.total >= self.emergency_cap
            if crossed_now:
                self.tripped = True
                self.trigger_role = actor
            return TokenUsageUpdate(
                total=self.total,
                tripped=self.tripped,
                crossed_now=crossed_now,
            )

    @property
    def snapshot(self) -> dict[str, Any]:
        """Return a deterministic JSON-ready final diagnostic."""
        return {
            "emergency_cap": self.emergency_cap,
            "total": self.total,
            "main": self.main,
            "child": self.child,
            "by_actor": dict(sorted(self.by_actor.items())),
            "tripped": self.tripped,
            "trigger_role": self.trigger_role,
        }
