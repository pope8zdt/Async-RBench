"""Canonical on-disk layout of an Async-RBench repository.

The case corpus and the registry that declares which cases are official are
addressed through these helpers, so the repository layout is stated once
instead of being re-spelled at every call site. This module imports nothing
from the rest of the package, so any layer may use it without a cycle.
"""

from __future__ import annotations

from pathlib import Path

# The benchmark ships its data beside the code, under a single data root.
DATA_RELPATH = Path("data") / "async-rbench"
CASES_RELPATH = DATA_RELPATH / "cases"
REGISTRY_RELPATH = DATA_RELPATH / "registry.json"


def cases_root(root: Path) -> Path:
    """Return the directory holding one sub-directory per registered case."""
    return root / CASES_RELPATH


def registered_case_dir(root: Path, case_id: str) -> Path:
    """Return the registered case's directory inside the case corpus."""
    return root / CASES_RELPATH / case_id


def registry_file(root: Path) -> Path:
    """Return the path of the registered-case registry."""
    return root / REGISTRY_RELPATH
