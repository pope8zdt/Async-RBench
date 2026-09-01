"""Normalizers and review scaffolding for multi-benchmark source evidence.

Async-RBench now curates evidence from four source families. Terminal-Bench uses
the Tracebench public trajectory pipeline. GAIA and Gaia2 supply official
scenario/event/Oracle-DAG structure when public model trajectories do not
exist. SWE-bench supplies official prediction/test evidence or SWE-agent
trajectories. Every evidence row keeps the same unified step schema:

    {"step_id": int, "role": user|agent|environment,
     "kind": task|action|observation|final,
     "content": str, "command": str, "source_ref": str}

The uniform step_id numbering lets trajectory-level and decision-point reviews
refer to the same evidence across all benchmarks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .trajectory_curation import _json_value

GAIA2_EVIDENCE_SCHEMA_VERSION = "1"


def _clip(value: Any, limit: int = 30000) -> str:
    text = str(value or "").replace("\x00", "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _event_action_text(action: dict[str, Any] | None) -> str:
    """Render an ARE event action as readable evidence text."""
    if not isinstance(action, dict):
        return str(action or "")
    app = str(action.get("app") or "")
    function = str(action.get("function") or "")
    op = str(action.get("operation_type") or "")
    args = action.get("args")
    rendered: list[str] = []
    if isinstance(args, list):
        for item in args:
            if not isinstance(item, dict):
                rendered.append(str(item))
                continue
            name = str(item.get("name") or "")
            value = item.get("value")
            if value is None:
                continue
            if isinstance(value, str):
                value = _clip(value, 1200)
            else:
                value = json.dumps(value, ensure_ascii=False)[:1200]
            rendered.append(f"{name}={value}")
    elif isinstance(args, dict):
        rendered = [f"{k}={_clip(v, 800)}" for k, v in args.items()]
    suffix = f" ({op})" if op and op not in ("None", "READ") else ""
    return f"{app}.{function}{suffix} [{', '.join(rendered)}]" if rendered else f"{app}.{function}{suffix}"


def normalize_gaia2_scenario(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert official Gaia2 events (USER/ENV/OracleEvent-AGENT) into steps.

    OracleEvent-AGENT events are the *oracle* action sequence, not a model
    trajectory. ENV events are world mutations the environment injects during
    the agent's work. source_ref always names the official event_id.
    """
    events = scenario.get("events") or []
    steps: list[dict[str, Any]] = []

    def user_text(event: dict[str, Any]) -> str:
        for item in (event.get("action") or {}).get("args") or []:
            if isinstance(item, dict) and item.get("name") == "content":
                return str(item.get("value") or "")
        return ""

    # Task step first (USER event), then remaining events in temporal order.
    user_events = [e for e in events if e.get("event_type") == "USER"]
    user_events.sort(key=lambda e: float(e.get("event_relative_time") or 0))
    for event in user_events:
        steps.append({
            "step_id": len(steps) + 1,
            "role": "user",
            "kind": "task",
            "content": _clip(user_text(event)),
            "source_ref": f"gaia2_event:{event.get('event_id')}",
        })

    ordered = sorted(
        (e for e in events if e.get("event_type") in {"ENV", "AGENT"}),
        key=lambda e: (float(e.get("event_relative_time") or 0), str(e.get("event_id"))),
    )
    for event in ordered:
        action = event.get("action") if isinstance(event.get("action"), dict) else {}
        app = str(action.get("app") or "")
        function = str(action.get("function") or "")
        event_type = event.get("event_type")
        if event_type == "ENV":
            role, kind = "environment", "observation"
            prefix = f"ENV event t={event.get('event_relative_time')}"
        else:
            role, kind = "agent", "action"
            prefix = f"Oracle action t={event.get('event_relative_time')}"
        deps = event.get("dependencies") or []
        deps_text = f" deps=[{', '.join(str(d)[:12] for d in deps)}]" if deps else ""
        content = f"{prefix}: {_event_action_text(action)}{deps_text}"
        step: dict[str, Any] = {
            "step_id": len(steps) + 1,
            "role": role,
            "kind": kind,
            "content": _clip(content),
            "source_ref": f"gaia2_event:{event.get('event_id')}",
            "app": app,
            "function": function,
        }
        steps.append(step)
    return steps


def scenario_summary(scenario: dict[str, Any]) -> dict[str, Any]:
    """Compact structural metadata for a Gaia2 scenario (used in inventory)."""
    events = scenario.get("events") or []
    return {
        "num_events": len(events),
        "num_env": sum(1 for e in events if e.get("event_type") == "ENV"),
        "num_oracle": sum(1 for e in events if e.get("event_type") == "AGENT"),
        "num_user": sum(1 for e in events if e.get("event_type") == "USER"),
        "apps": sorted({str((e.get("action") or {}).get("app") or "") for e in events}),
        "has_dependencies": any(e.get("dependencies") for e in events),
    }


def gaia2_review_record(
    scenario_id: str, scenario: dict[str, Any], *,
    split: str, category: str, source_sha256: str,
) -> dict[str, Any]:
    """Review record for a Gaia2 scenario following the trajectory schema."""
    steps = normalize_gaia2_scenario(scenario)
    return {
        "review_id": f"gaia2:{scenario_id}",
        "task_name": scenario_id,
        "source": {
            "benchmark": "gaia2", "scenario_id": scenario_id, "split": split,
            "category": category, "source_sha256": source_sha256,
            "trajectory_origin": "structure_derived_from_official_scenario",
            "artifact_path": f"raw/gaia2/{scenario_id}.json",
        },
        "machine_screen": {
            "manifest_solved": None,
            "step_count": len(steps),
            "stage_count": 0,
            "selection_reasons": ["official_scenario_structure", "oracle_action_dag"],
        },
        "agent_coarse_label": {
            "status": "pending", "trajectory_quality": "pending",
            "failure_attribution": "pending", "replanning_evidence": "pending",
            "research_events": [], "candidate_decision_count": 0,
            "evidence_step_ids": [],
        },
        "human_review": {
            "review_decision": "pending", "task_match": "pending",
            "version_match": "pending", "trajectory_quality": "pending",
            "failure_attribution": "pending", "replanning_evidence": "pending",
            "research_events": [], "recommended_uses": [],
            "evidence_step_ids": [], "reviewer_note": "",
        },
    }


def normalize_swebench_prediction(instance: dict[str, Any], steps_source: str) -> list[dict[str, Any]]:
    """Build a step list from SWE-bench instance/prediction evidence.

    ``steps_source`` is either a normalized trajectory already in the unified
    step schema (returned unchanged) or an iterable of raw event dicts handled
    by the caller. This function only records the instance contract so that a
    trajectory-derived review can cite the official instance facts.
    """
    if isinstance(steps_source, list) and steps_source and isinstance(steps_source[0], dict):
        first = steps_source[0]
        if "step_id" in first and "role" in first:
            return steps_source
    raise ValueError("normalize_swebench_prediction expects unified step rows")


def gaia2_scenario_from_parquet(
    parquet: Path, scenario_id: str, *, con_driver: Any | None = None,
) -> dict[str, Any]:
    """Load one Gaia2 scenario JSON from the mini parquet via duckdb.

    Falls back to a local per-scenario JSON file when already extracted.
    """
    local = parquet.parent / f"{scenario_id}.json"
    if local.is_file():
        return json.loads(local.read_text(encoding="utf-8"))
    import duckdb  # local import keeps the module importable without duckdb
    if con_driver is None:
        con_driver = duckdb.connect()
    row = con_driver.execute(
        f"SELECT data FROM read_parquet('{parquet.as_posix()}') WHERE scenario_id = ?",
        [scenario_id],
    ).fetchone()
    if not row:
        raise ValueError(f"scenario {scenario_id!r} not found in {parquet}")
    value = json.loads(row[0])
    local.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    return value


def gaia2_scenarios_from_parquet(parquet: Path) -> list[tuple[str, str, dict[str, Any]]]:
    """Return (scenario_id, category, scenario) for every row in the mini parquet."""
    import duckdb
    con = duckdb.connect()
    rows = con.execute(
        f"SELECT scenario_id, category, data FROM read_parquet('{parquet.as_posix()}')"
    ).fetchall()
    return [(str(r[0]), str(r[1]), json.loads(r[2])) for r in rows]
