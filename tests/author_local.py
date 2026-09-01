"""Skip guards for tests that require author-local (non-vendored) resources.

The published repository deliberately does not vendor large author-local
inputs: upstream source trees (``upstream/*``), production data
(``candidate_cases/``, ``candidate_instances/``) and runtime artifacts
(``artifacts/*``). Tests that depend on them skip with an explicit reason
when the resource is absent, so a fresh clone runs green while the author
machine still runs the checks strictly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def requires_author_local(*relpaths: str):
    """Return a skipif mark that skips when any author-local path is absent.

    Each ``relpath`` is relative to the repository root. The mark applies to
    the decorated test(s) (or to the whole module via ``pytestmark``).
    """
    missing = sorted(
        relpath for relpath in relpaths if not (ROOT / relpath).exists()
    )
    return pytest.mark.skipif(
        bool(missing),
        reason=(
            "author-local resource is not part of the repository checkout: "
            + ", ".join(missing)
        ),
    )
