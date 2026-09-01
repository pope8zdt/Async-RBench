"""Stable runtime API for generated Docker-backed case packages.

Generated cases import this module so their small entry points do not depend
on the internal filename that contains the Docker implementation.
"""

from pathlib import Path

from .docker_case import export_task as _export_task
from .docker_case import run_oracle as _run_oracle
from .docker_case import run_verifier as _run_verifier


def export_task(case_dir: Path, case_id: str) -> None:
    _export_task(case_dir, case_id)


def _case_id(args: tuple[object, ...]) -> str:
    if len(args) == 1:
        return str(args[0])
    if len(args) == 2:
        return str(args[1])
    raise TypeError("expected case_id or (case_dir, case_id)")


def run_oracle(*args: object) -> None:
    _run_oracle(_case_id(args))


def run_verifier(*args: object) -> None:
    _run_verifier(_case_id(args))

__all__ = ["export_task", "run_oracle", "run_verifier"]
