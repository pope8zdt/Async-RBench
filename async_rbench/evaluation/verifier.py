from __future__ import annotations

"""Kernel-facing verifier surface.

The heavy lifting (hidden-test injection, filesystem-snapshot clone, audit)
lives in ``async_rbench.private_eval``; this module is the thin, stable entry point
the rest of the kernel imports, so the private verifier can evolve without the
kernel changing its imports.
"""

from ..private_eval import (
    PrivateVerificationResult,
    audit_participant_container,
    run_isolated_verifier,
    verifier_bundle_sha256,
)


def run_verifier(
    *, main_container: str, task_dir, episode_id: str, timeout_sec: int = 1800
) -> PrivateVerificationResult:
    """Verify a frozen filesystem clone the participant cannot access."""
    return run_isolated_verifier(
        main_container=main_container,
        task_dir=task_dir,
        episode_id=episode_id,
        timeout_sec=timeout_sec,
    )


__all__ = [
    "run_verifier",
    "run_isolated_verifier",
    "verifier_bundle_sha256",
    "audit_participant_container",
    "PrivateVerificationResult",
]
