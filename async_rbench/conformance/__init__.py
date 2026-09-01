"""Conformance / Runtime / Replay tool layer (Layer 4).

Protocol conformance is a gate, not a score: ``conformance_passed`` is an
audit field on every episode. The suite tests only protocol invariants and
never task capability.
"""

from __future__ import annotations

from .runner import conformance_adapter_command, run_conformance
from .suite import CONFORMANCE_TESTS, CheckResult, run_checks

__all__ = [
    "CONFORMANCE_TESTS",
    "CheckResult",
    "run_checks",
    "run_conformance",
    "conformance_adapter_command",
]
