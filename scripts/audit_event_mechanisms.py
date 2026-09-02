from __future__ import annotations

"""Task 1 of the Async-RBench event-migration redesign.

Freeze the event-mechanism protocol version and generate a registry-driven
inventory of every registered ``(case_id, instance_id)`` with its current and
required stimulus data. The official registry is loaded through
``async_rbench.spec`` (never by counting directories directly); every instance
is resolved, its private event contracts are read, and each primary theme is
mapped to its allowed stimulus types from ``event_taxonomy.json``.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from async_rbench.evaluation.event_taxonomy import (
    STIMULUS_EVENT_TYPES,
    load_event_taxonomy,
)
from async_rbench.spec import discover_case_instances

# ---------------------------------------------------------------------------
# Frozen protocol artifacts + taxonomy
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = REPO_ROOT / "event_taxonomy.json"

TAXONOMY = load_event_taxonomy(TAXONOMY_PATH)
EVENT_THEMES: dict[str, dict[str, Any]] = {
    str(item["id"]): item for item in TAXONOMY.get("event_themes", [])
}
MANIFEST_FREEZE = TAXONOMY.get("manifest_freeze") or {}
FROZEN_PROTOCOL_VERSION = str(MANIFEST_FREEZE.get("protocol_version") or "1.0")
# Frozen plan expectation. This is a recorded plan value, never an assignment
# source: the classification is computed from real contract data and then
# *checked* against this constant (see `_collect_discrepancies`).
FROZEN_THEME_DISTRIBUTION: dict[str, int] = {
    str(theme_id): int(count)
    for theme_id, count in (MANIFEST_FREEZE.get("frozen_theme_distribution") or {}).items()
}

SENTINEL = "not_declared"
SCHEMA_VERSION = "1.0"

# Fields that must be present on every manifest row.
REQUIRED_ROW_FIELDS = (
    "case_id",
    "instance_id",
    "split",
    "primary_event_theme",
    "current_stimulus_type",
    "required_stimulus_type",
    "current_trigger",
    "required_trigger",
    "event_id",
    "provisional_predicate",
    "required_changes",
    "required_preservation",
    "forbidden_changes",
    "closure_checks",
    "migration_class",
    "migration_status",
    "row_digest",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _join(values: Any) -> str:
    """Deterministically render a scalar/list-of-scalars as a ``|`` string."""
    if values is None:
        return SENTINEL
    if isinstance(values, str):
        return values.strip() or SENTINEL
    if isinstance(values, (list, tuple, set)):
        rendered = sorted({str(item).strip() for item in values if str(item).strip()})
        return "|".join(rendered) if rendered else SENTINEL
    return str(values).strip() or SENTINEL


def _current_stimulus_types(raw: dict[str, Any]) -> list[str]:
    """Distinct stimulus kinds scheduled by the case's async scenario.

    Reads the shared-contract ``stimulus_type`` field (Task 10 swimlane 0a) so the
    manifest reflects the declared kind instead of the legacy ``result_delivery``
    default that ignored the tag.  An event without a recognised ``stimulus_type``
    is read as ``result_delivery``, matching ``event_taxonomy.scenario_event_type``.
    """
    events = (((raw.get("scenarios") or {}).get("async") or {}).get("events") or [])
    kinds: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = str(event.get("stimulus_type") or "")
        kinds.add(kind if kind in STIMULUS_EVENT_TYPES else "result_delivery")
    return sorted(kinds)


def _current_triggers(raw: dict[str, Any]) -> list[str]:
    """Distinct non-empty evaluator trigger boundaries used by async events."""
    events = (((raw.get("scenarios") or {}).get("async") or {}).get("events") or [])
    return sorted({
        str(event["trigger"]) for event in events
        if isinstance(event, dict) and str(event.get("trigger") or "").strip()
    })


def _derive_row(
    *,
    case_id: str,
    instance_id: str,
    split: str,
    case_dir: Path,
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Derive one plan row from the registry instance and its private contracts.

    Field-name mapping (existing contract data -> plan field name):

      required_behavior / after_state          -> required_changes
      forbidden_behavior / forbidden_shortcut  -> forbidden_changes
      before_state                             -> provisional_predicate
      unaffected_nodes / must_still_pass       -> required_preservation
      affected_closure (+ affected/unaffected nodes) -> closure_checks
      mutation_family                          -> migration_class
      event_id (contract)                      -> event_id

    Missing data is reported with the SENTINEL instead of being fabricated so
    the migration status reflects real coverage gaps.

    ``case_dir`` is the registry-resolved instance directory (``cases/<case_id>``
    for path ``.``, or the nested ``instances/<id>`` directory otherwise), so the
    per-instance private contracts are read from the correct location.
    """
    private_dir = case_dir / "private"

    event_policy = _read_json(private_dir / "event_policy.json") or {}
    case_ir = _read_json(private_dir / "case_ir.json") or {}

    contract = event_policy.get("event_contract") or {}
    ir_contract = case_ir.get("event_contract") or {}
    decision_contracts = [d for d in (case_ir.get("decision_contracts") or []) if isinstance(d, dict)]

    primary_theme = str((raw.get("classification") or {}).get("primary_event_theme") or SENTINEL)
    theme_def = EVENT_THEMES.get(primary_theme) or {}

    # An unrecognized theme still yields a row (coverage gap must be reported),
    # with the required stimulus left as the SENTINEL rather than raising.
    required_stimulus = _join(theme_def.get("stimulus_event_types") or [])

    current_types = _current_stimulus_types(raw)
    current_stimulus = _join(current_types) if current_types else SENTINEL
    current_trigger = _join(_current_triggers(raw))

    # event_id: contract explicit id -> ir event_contract id -> first scenario id.
    event_id = event_policy.get("event_id") or ir_contract.get("event_id") or SENTINEL
    if event_id == SENTINEL:
        events = (((raw.get("scenarios") or {}).get("async") or {}).get("events") or [])
        if events and isinstance(events[0], dict) and str(events[0].get("id") or "").strip():
            event_id = str(events[0]["id"])

    first_decision = decision_contracts[0] if decision_contracts else {}
    # first mutation_family anywhere in the decision contracts.
    mutation_family = next(
        (str(d["mutation_family"]) for d in decision_contracts
         if d.get("mutation_family") not in (None, "")),
        SENTINEL,
    )

    provisional_predicate = contract.get("before_state") or ir_contract.get("before_state")
    required_preservation = (
        _join(contract.get("unaffected_nodes"))
        if contract.get("unaffected_nodes")
        else _join(ir_contract.get("unaffected_nodes"))
    )
    if required_preservation == SENTINEL:
        must_still_pass = first_decision.get("must_still_pass")
        if must_still_pass:
            required_preservation = _join(must_still_pass)

    required_changes = first_decision.get("required_behavior")
    if not required_changes:
        required_changes = contract.get("after_state") or ir_contract.get("after_state")

    forbidden_changes = first_decision.get("forbidden_behavior")
    if not forbidden_changes:
        forbidden_changes = event_policy.get("forbidden_shortcut")

    closure_sources = []
    for source in (contract.get("affected_closure"), ir_contract.get("affected_closure")):
        if source:
            closure_sources.extend(source)
    if not closure_sources:
        for nodes_key in ("affected_nodes", "unaffected_nodes"):
            nodes = contract.get(nodes_key) or ir_contract.get(nodes_key)
            if nodes:
                closure_sources.extend(nodes)
    closure_checks = _join(closure_sources)

    migration_class = mutation_family

    # Migration status: a case whose current stimulus already sits inside the
    # theme's frozen stimulus set needs no stimulus migration. An unknown theme
    # has no declared stimulus set, so it is never confirmed as matching.
    if current_stimulus != SENTINEL and set(current_types) <= set(
        theme_def.get("stimulus_event_types") or []
    ):
        migration_status = "matches_frozen_stimulus"
    else:
        migration_status = "needs_stimulus_migration"

    row = {
        "case_id": case_id,
        "instance_id": instance_id,
        "split": split,
        "primary_event_theme": primary_theme,
        "current_stimulus_type": current_stimulus,
        "required_stimulus_type": required_stimulus,
        "current_trigger": current_trigger,
        "required_trigger": SENTINEL,  # taxonomy declares no evaluator trigger boundary
        "event_id": event_id,
        "provisional_predicate": _join(provisional_predicate),
        "required_changes": _join(required_changes),
        "required_preservation": required_preservation,
        "forbidden_changes": _join(forbidden_changes),
        "closure_checks": closure_checks,
        "migration_class": _join(migration_class),
        "migration_status": migration_status,
    }
    row["row_digest"] = _row_digest(row)
    return row


def _row_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _collect_discrepancies(
    computed: dict[str, int], rows: list[dict[str, Any]]
) -> list[str]:
    """Report every theme whose computed instance count differs from the frozen
    plan, listing the affected instance ids instead of silently coercing the
    count to match."""
    discrepancies: list[str] = []
    themes = set(FROZEN_THEME_DISTRIBUTION) | set(computed)
    for theme_id in sorted(themes):
        expected = FROZEN_THEME_DISTRIBUTION.get(theme_id, 0)
        actual = computed.get(theme_id, 0)
        if expected == actual:
            continue
        instance_ids = sorted(
            f"{row['case_id']}/{row['instance_id']}"
            for row in rows if row["primary_event_theme"] == theme_id
        )
        discrepancies.append(
            f"{theme_id}: frozen plan expects {expected} instance(s) but manifest selects "
            f"{actual}; selected ids = {instance_ids}"
        )
    return discrepancies


def build_event_migration_manifest(root: Path) -> dict[str, Any]:
    """Registry-driven migration manifest over every registered instance."""
    instances = discover_case_instances(Path(root))
    rows: list[dict[str, Any]] = []
    for instance in instances:
        raw = instance.load().raw
        rows.append(_derive_row(
            case_id=instance.case_id,
            instance_id=instance.instance_id,
            split=instance.split,
            case_dir=instance.case_dir,
            raw=raw,
        ))

    rows.sort(key=lambda r: (r["case_id"], r["instance_id"]))

    # Count every actual theme present in the rows (including any theme that is
    # not in the taxonomy), so an unknown theme surfaces as a discrepancy rather
    # than being silently dropped from the inventory.
    themed = {row["primary_event_theme"] for row in rows}
    theme_counts = {
        theme_id: sum(1 for row in rows if row["primary_event_theme"] == theme_id)
        for theme_id in sorted(themed)
    }
    status_counts = {
        status: sum(1 for row in rows if row["migration_status"] == status)
        for status in sorted({row["migration_status"] for row in rows})
    }
    stimulus_counts = {
        stimulus: sum(1 for row in rows if row["required_stimulus_type"] == stimulus)
        for stimulus in sorted({row["required_stimulus_type"] for row in rows})
    }
    current_stimulus_counts = {
        stimulus: sum(1 for row in rows if row["current_stimulus_type"] == stimulus)
        for stimulus in sorted({row["current_stimulus_type"] for row in rows})
    }

    summary = {
        "primary_event_theme_counts": theme_counts,
        "migration_status_counts": status_counts,
        "required_stimulus_counts": stimulus_counts,
        "current_stimulus_counts": current_stimulus_counts,
    }
    discrepancies = _collect_discrepancies(theme_counts, rows)
    valid = not discrepancies

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": FROZEN_PROTOCOL_VERSION,
        "instance_count": len(rows),
        "rows": rows,
        "summary": summary,
        "discrepancies": discrepancies,
        "valid": valid,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repo root (default: cwd)")
    parser.add_argument(
        "--output",
        default="research/experiment-design/async-rbench-event-migration-manifest.json",
        help="Output path for the generated manifest",
    )
    args = parser.parse_args(argv)

    manifest = build_event_migration_manifest(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"wrote {output}: {manifest['instance_count']} instances, valid={manifest['valid']}")
    for discrepancy in manifest["discrepancies"]:
        print(f"  DISCREPANCY: {discrepancy}")
    return 0 if manifest["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
