from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .event_taxonomy import ASYNC_SCENARIO_CLASSES, EVENT_THEME_IDS


def build_event_coverage(cases: Iterable[Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    primary_counts: Counter[str] = Counter()
    secondary_counts: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    capability_counts: Counter[str] = Counter()
    event_capability: dict[str, Counter[str]] = defaultdict(Counter)
    errors: list[str] = []
    for case in cases:
        raw = case.raw if hasattr(case, "raw") else case.load().raw
        instance_id = getattr(case, "instance_id", "seed-1")
        classification = raw.get("classification") or {}
        primary = str(classification.get("primary_event_theme") or "")
        secondary = [str(item) for item in classification.get("secondary_event_themes") or []]
        scenario_class = str(classification.get("async_scenario_class") or "")
        capabilities = sorted(str(item) for item in raw.get("capabilities") or [])
        if primary not in EVENT_THEME_IDS:
            errors.append(f"{case.case_id}: missing or invalid primary event theme")
        if scenario_class not in ASYNC_SCENARIO_CLASSES:
            errors.append(f"{case.case_id}: missing or invalid async scenario class")
        primary_counts[primary] += 1
        secondary_counts.update(secondary)
        scenario_counts[scenario_class] += 1
        capability_counts.update(capabilities)
        event_capability[primary].update(capabilities)
        rows.append({
            "case_id": case.case_id,
            "instance_id": instance_id,
            "primary_event_theme": primary,
            "secondary_event_themes": secondary,
            "async_scenario_class": scenario_class,
            "capabilities": capabilities,
        })
    missing = sorted(EVENT_THEME_IDS - set(primary_counts))
    return {
        "schema_version": "1.0",
        "case_count": len(rows),
        "counting_rule": (
            "primary_event_theme counts each registered instance exactly once; capability counts are "
            "independent multi-label totals"
        ),
        "primary_event_theme_counts": dict(sorted(primary_counts.items())),
        "secondary_event_theme_counts": dict(sorted(secondary_counts.items())),
        "async_scenario_class_counts": dict(sorted(scenario_counts.items())),
        "capability_counts": dict(sorted(capability_counts.items())),
        "event_capability_cross_tab": {
            theme: dict(sorted(counts.items()))
            for theme, counts in sorted(event_capability.items())
        },
        "missing_primary_event_themes": missing,
        "rows": sorted(rows, key=lambda item: (item["case_id"], item["instance_id"])),
        "valid": not errors,
        "errors": errors,
    }


def write_event_coverage(path: Path, report: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
