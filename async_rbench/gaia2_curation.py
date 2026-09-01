"""Deterministic curation of causal late-event graphs from pinned GAIA2 data."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


SELECTION_RULE = "gaia2-direct-env-causal-bridge-v1"


def _public_value(value: Any) -> str:
    """Remove opaque source-graph identifiers from annotator-facing text."""
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\{\{(?:OracleEvent|Event)-[^{}]+\}\}", "[先前步骤结果]", text)
    text = re.sub(
        r"(?:OracleEvent|Event)-(?:AGENT|ENV|USER)-[A-Za-z0-9-]+",
        "[内部事件]",
        text,
    )
    return text


def _action_text(event: dict[str, Any], limit: int = 520) -> str:
    action = event.get("action") or {}
    app = str(action.get("app") or "Environment")
    function = str(action.get("function") or "event")
    args = []
    for item in action.get("args") or []:
        if not isinstance(item, dict):
            continue
        value = _public_value(item.get("value"))
        if len(value) > 180:
            value = value[:180] + "…"
        args.append(f"{item.get('name')}={value}")
    text = f"{app}.{function}({', '.join(args[:5])})"
    return text[:limit] + ("…" if len(text) > limit else "")


def _user_goal(events: list[dict[str, Any]]) -> str:
    for event in events:
        if event.get("class_name") == "Event" and event.get("event_type") == "USER":
            for item in ((event.get("action") or {}).get("args") or []):
                if item.get("name") == "content" and str(item.get("value") or "").strip():
                    return str(item["value"]).strip()
    return "Complete the task described by the dynamic environment scenario."


def build_gaia2_review_records(
    rows: Iterable[dict[str, Any]], *, limit: int = 50,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        data_value = row.get("data")
        data = json.loads(data_value) if isinstance(data_value, str) else data_value
        if not isinstance(data, dict):
            continue
        events = [event for event in data.get("events") or [] if isinstance(event, dict)]
        by_id = {str(event.get("event_id") or ""): event for event in events}
        oracle = [
            event for event in events
            if event.get("class_name") == "OracleEvent" and event.get("event_type") == "AGENT"
        ]
        causal: list[tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = []
        for event in events:
            if event.get("class_name") != "Event" or event.get("event_type") != "ENV":
                continue
            prior = [
                by_id[dependency] for dependency in event.get("dependencies") or []
                if dependency in by_id and by_id[dependency].get("class_name") == "OracleEvent"
            ]
            affected = [
                candidate for candidate in oracle
                if event.get("event_id") in (candidate.get("dependencies") or [])
            ]
            if prior and affected:
                causal.append((event, prior, affected))
        if not causal:
            continue
        late, prior, affected = sorted(
            causal,
            key=lambda item: (-len(item[2]), float(item[0].get("event_relative_time") or 0)),
        )[0]
        selected.append((row, prior[-1], late, affected[0]))
    selected.sort(key=lambda item: (str(item[0].get("category") or ""), str(item[0].get("scenario_id") or "")))
    records: list[dict[str, Any]] = []
    source_map: list[dict[str, Any]] = []
    for ordinal, (row, prior, late, affected) in enumerate(selected[:limit], 1):
        raw_data = row.get("data")
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        blind_id = f"gaia2-calibration-b001-{ordinal:03d}"
        events = list((data or {}).get("events") or [])
        prior_text, late_text, affected_text = map(
            _action_text, (prior, late, affected),
        )
        public_steps = {
            str(prior.get("event_id")): ("步骤1", "场景中的既有动作"),
            str(late.get("event_id")): ("步骤2", "外部环境事件"),
            str(affected.get("event_id")): ("步骤3", "场景要求的后续动作"),
        }
        records.append({
            "schema_version": "3",
            "review_id": blind_id,
            "review_round": 1,
            "source": {
                "benchmark": "dynamic-environment",
                "task_id": blind_id,
                "trajectory_id": blind_id,
            },
            "task_goal": _user_goal(events),
            "evidence_card": {
                "prior_work": {
                    "summary": "场景依赖图表明，在外部事件发生前，这项工作已经完成或进入既定状态。",
                    "excerpts": [{
                        "step_id": "步骤1",
                        "actor": "场景中的既有动作", "text": prior_text,
                    }],
                },
                "late_information": {
                    "summary": "随后由环境独立触发了新的状态或消息。",
                    "excerpts": [{
                        "step_id": "步骤2",
                        "actor": "外部环境事件", "text": late_text,
                    }],
                },
                "affected_action": {
                    "summary": "场景依赖图将下面的后续动作直接绑定到该外部事件。",
                    "excerpts": [{
                        "step_id": "步骤3",
                        "actor": "场景要求的后续动作", "text": affected_text,
                    }],
                },
                "expanded_context": [
                    {"step_id": public_steps[str(event.get("event_id"))][0],
                     "actor": public_steps[str(event.get("event_id"))][1],
                     "text": _action_text(event)}
                    for event in events
                    if event.get("event_id") in {
                        prior.get("event_id"), late.get("event_id"), affected.get("event_id")
                    }
                ],
            },
        })
        canonical = raw_data if isinstance(raw_data, str) else json.dumps(
            raw_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        source_map.append({
            "blind_review_id": blind_id,
            "scenario_id": str(row.get("scenario_id") or ""),
            "category": str(row.get("category") or ""),
            "source_row_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "prior_event_id": str(prior.get("event_id") or ""),
            "late_event_id": str(late.get("event_id") or ""),
            "affected_event_id": str(affected.get("event_id") or ""),
            "selection_rule": SELECTION_RULE,
        })
    return records, source_map


def read_gaia2_parquet(path: Path) -> list[dict[str, Any]]:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - environment dependency message
        raise RuntimeError("duckdb is required to read the pinned GAIA2 parquet") from exc
    connection = duckdb.connect()
    columns = {
        str(row[0]) for row in connection.execute(
            "describe select * from read_parquet(?)", [str(path)]
        ).fetchall()
    }
    selected = ["id", "scenario_id", "split", "data"]
    if "category" in columns:
        selected.append("category")
    result = connection.execute(
        f"select {', '.join(selected)} from read_parquet(?)", [str(path)]
    )
    columns = [item[0] for item in result.description]
    rows = [dict(zip(columns, row)) for row in result.fetchall()]
    fallback_category = path.parent.name
    for row in rows:
        row.setdefault("category", fallback_category)
    return rows
