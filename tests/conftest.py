from __future__ import annotations

from pathlib import Path

import pytest

from async_rbench.evaluation.audit import audit_contract_fixtures


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def contract_fixtures() -> dict:
    """The full-corpus contract-fixture audit, computed once per test session.

    ``test_audit`` used to re-run this subprocess-heavy scan three times: once
    directly, once inside ``audit_run``, and once to cross-check the observation
    coverage.  Sharing one session-scoped snapshot and threading it into
    ``audit_run(contract_fixtures=...)`` turns that into a single pass.
    """
    return audit_contract_fixtures(ROOT)
