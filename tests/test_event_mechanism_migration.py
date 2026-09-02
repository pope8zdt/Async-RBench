from __future__ import annotations

from pathlib import Path

from scripts.audit_event_mechanisms import (
    FROZEN_THEME_DISTRIBUTION,
    build_event_migration_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def test_event_migration_manifest_covers_every_registered_instance() -> None:
    report = build_event_migration_manifest(ROOT)
    assert report["instance_count"] == 201
    assert len(report["rows"]) == 201
    assert len({(r["case_id"], r["instance_id"]) for r in report["rows"]}) == 201
    assert all(r["required_stimulus_type"] for r in report["rows"])


def test_event_migration_manifest_matches_frozen_theme_distribution() -> None:
    report = build_event_migration_manifest(ROOT)
    computed = report["summary"]["primary_event_theme_counts"]
    assert computed == FROZEN_THEME_DISTRIBUTION


def test_event_migration_manifest_is_deterministic() -> None:
    first = build_event_migration_manifest(ROOT)
    second = build_event_migration_manifest(ROOT)
    assert first["rows"] == second["rows"]
    assert first["summary"] == second["summary"]


def test_event_migration_manifest_discrepancies_are_listed() -> None:
    report = build_event_migration_manifest(ROOT)
    assert report["discrepancies"] == []
    assert report["valid"] is True
