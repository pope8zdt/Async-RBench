from __future__ import annotations

from typing import Any, Iterable

from .case_contract import assert_participant_safe, find_private_fields


def audit_participant_view(surfaces: Iterable[tuple[str, Any]]) -> list[str]:
    """Audit already-rendered model/adapter surfaces for private field names."""
    errors: list[str] = []
    for name, value in surfaces:
        for path in find_private_fields(value):
            errors.append(f"{name}: private field at {path}")
    return errors


def require_safe_participant_view(surfaces: Iterable[tuple[str, Any]]) -> None:
    for name, value in surfaces:
        assert_participant_safe(value, surface=name)
