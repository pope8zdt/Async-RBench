from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "event_taxonomy.json"


def load_event_taxonomy(path: Path | None = None) -> dict[str, Any]:
    value = json.loads((path or TAXONOMY_PATH).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("event taxonomy must be a JSON object")
    return value


EVENT_TAXONOMY = load_event_taxonomy()
EVENT_THEME_IDS = frozenset(
    str(item["id"]) for item in EVENT_TAXONOMY.get("event_themes", [])
)
ASYNC_SCENARIO_CLASSES = frozenset(
    str(item) for item in EVENT_TAXONOMY.get("async_scenario_classes", [])
)
STIMULUS_EVENT_TYPES = frozenset(
    str(item) for item in EVENT_TAXONOMY.get("stimulus_event_types", [])
)
RESULT_BEARING_EVENT_TYPES = frozenset({"result_delivery", "implicit_error_result"})
# Schedule-row kinds that may declare a ``result`` role.  The role names the real
# completion that row governs (delivery rows must carry one); revision / pressure
# / terminal rows carry one when the specialised stimulus is attached to a result
# (the in-tree swe/tbn cases tag their after_artifacts authority rows), and may
# omit it when the row is a pure live mechanism with no delivery of its own.
# ``completion_replay`` (replay_of_result) and ``deadline_update`` (no result)
# never declare a plain ``result`` role.
RESULT_CAPABLE_EVENT_TYPES = STIMULUS_EVENT_TYPES - {
    "completion_replay", "deadline_update",
}
WORKSTREAM_EVENT_TYPES = frozenset({
    "child_timeout", "child_crash", "resource_pressure", "deadline_update",
})
REVISION_EVENT_TYPES = frozenset({"task_scope_revision", "dependency_graph_revision"})


def validate_event_taxonomy(path: Path | None = None) -> list[str]:
    try:
        taxonomy = load_event_taxonomy(path)
    except (OSError, ValueError, TypeError) as exc:
        return [f"invalid event taxonomy: {exc}"]
    errors: list[str] = []
    if taxonomy.get("execution_modes") != ["linear", "async"]:
        errors.append("event taxonomy execution_modes must be exactly linear and async")
    themes = list(taxonomy.get("event_themes") or [])
    theme_ids = [str(item.get("id") or "") for item in themes if isinstance(item, dict)]
    if len(themes) != 8 or len(theme_ids) != 8 or len(set(theme_ids)) != 8:
        errors.append("event taxonomy must define exactly eight unique event themes")
    scenario_classes = set(taxonomy.get("async_scenario_classes") or [])
    if scenario_classes != {"result_eventful", "live_eventful", "resource_eventful"}:
        errors.append("event taxonomy must define the three frozen async scenario classes")
    stimulus_types = set(taxonomy.get("stimulus_event_types") or [])
    for item in themes:
        if not isinstance(item, dict):
            errors.append("event taxonomy theme entries must be objects")
            continue
        if not str(item.get("description") or "").strip():
            errors.append(f"event theme {item.get('id')!r} is missing a description")
        allowed_classes = set(item.get("allowed_scenario_classes") or [])
        if not allowed_classes or allowed_classes - scenario_classes:
            errors.append(f"event theme {item.get('id')!r} has invalid scenario classes")
        declared_types = set(item.get("stimulus_event_types") or [])
        if not declared_types or declared_types - stimulus_types:
            errors.append(f"event theme {item.get('id')!r} has invalid stimulus event types")
    if not str(taxonomy.get("counting_rule") or "").strip():
        errors.append("event taxonomy must state the event/capability counting rule")
    if not str(taxonomy.get("trajectory_policy") or "").strip():
        errors.append("event taxonomy must state the non-scoring trajectory policy")
    return errors


def validate_case_classification(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return ["classification must be an object"]
    errors: list[str] = []
    primary = str(value.get("primary_event_theme") or "")
    secondary_raw = value.get("secondary_event_themes")
    scenario_class = str(value.get("async_scenario_class") or "")
    if primary not in EVENT_THEME_IDS:
        errors.append(f"unknown primary_event_theme {primary!r}")
    if not isinstance(secondary_raw, list):
        errors.append("secondary_event_themes must be a list")
        secondary: list[str] = []
    else:
        secondary = [str(item) for item in secondary_raw]
        if len(secondary) != len(set(secondary)):
            errors.append("secondary_event_themes must be unique")
        unknown = set(secondary) - EVENT_THEME_IDS
        if unknown:
            errors.append(f"unknown secondary_event_themes {sorted(unknown)!r}")
        if primary in secondary:
            errors.append("primary_event_theme must not also be secondary")
    if scenario_class not in ASYNC_SCENARIO_CLASSES:
        errors.append(f"unknown async_scenario_class {scenario_class!r}")
    theme = next(
        (item for item in EVENT_TAXONOMY["event_themes"] if item["id"] == primary),
        None,
    )
    if theme is not None and scenario_class not in set(theme["allowed_scenario_classes"]):
        errors.append(
            f"primary event theme {primary!r} is incompatible with "
            f"async_scenario_class {scenario_class!r}"
        )
    return errors


def scenario_event_type(event: Mapping[str, Any]) -> str:
    """Return the stimulus kind a scenario/schedule event declares.

    The shared contract field is ``stimulus_type`` (Task 10 swimlane 0a); the
    legacy ``type`` reads treated every row that did not carry ``type`` as
    ``result_delivery`` and silently ignored the declared ``stimulus_type`` tag.
    A declared kind that is not a frozen ``stimulus_event_types`` member is read
    as ``result_delivery`` (the plain scheduled-delivery row), so pre-migration
    contracts that stamped a theme name as the tag keep their delivery semantics.
    """
    kind = str(event.get("stimulus_type") or "")
    if kind in STIMULUS_EVENT_TYPES:
        return kind
    return "result_delivery"


def validate_scenario_events(
    events: Any,
    *,
    execution_mode: str,
    allowed_results: Iterable[str],
    workstream_ids: Iterable[str],
    known_artifacts: Iterable[str],
    known_milestones: Iterable[str],
) -> list[str]:
    if not isinstance(events, list):
        return [f"{execution_mode} scenario events must be a list"]
    errors: list[str] = []
    allowed = {str(item) for item in allowed_results}
    workstreams = {str(item) for item in workstream_ids}
    artifacts = {str(item) for item in known_artifacts}
    milestones = {str(item) for item in known_milestones}
    seen_ids: set[str] = set()
    result_events: list[str] = []
    replay_events: list[tuple[str, str]] = []
    for index, event in enumerate(events):
        prefix = f"{execution_mode} scenario events[{index}]"
        if not isinstance(event, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        event_id = str(event.get("id") or "")
        if not event_id or event_id in seen_ids:
            errors.append(f"{prefix} id must be non-empty and unique")
        seen_ids.add(event_id)
        event_type = scenario_event_type(event)
        if event_type not in STIMULUS_EVENT_TYPES:
            errors.append(f"{prefix} has unsupported event type {event_type!r}")
            continue
        if execution_mode == "linear":
            errors.append("linear scenario must not inject evaluator events")
        result = event.get("result")
        if event_type in RESULT_BEARING_EVENT_TYPES:
            # Pure delivery rows: a result role is mandatory.
            if str(result or "") not in allowed:
                errors.append(f"{prefix} result is missing from result_contract")
            else:
                result_events.append(str(result))
        elif event_type in RESULT_CAPABLE_EVENT_TYPES:
            # Optional result role: when present it is a delivery row for that
            # result kind (and is scheduled like any other delivery); when absent
            # the row is a pure live mechanism fired at a child boundary.
            if result is not None:
                if str(result) not in allowed:
                    errors.append(f"{prefix} result is missing from result_contract")
                else:
                    result_events.append(str(result))
        elif result is not None:
            errors.append(f"{prefix} type {event_type!r} must not declare result")
        if event_type == "completion_replay":
            replay_of = str(event.get("replay_of_result") or "")
            if replay_of not in allowed:
                errors.append(f"{prefix} replay_of_result is missing from result_contract")
            if event.get("trigger") != "after_consumed":
                errors.append(f"{prefix} completion replay trigger must be 'after_consumed'")
            replay_events.append((event_id, replay_of))
        elif event_type in RESULT_CAPABLE_EVENT_TYPES and result is not None:
            trigger = event.get("trigger")
            if trigger not in {
                None, "after_artifacts_committed", "after_results_delivered",
            }:
                errors.append(
                    f"{prefix} result trigger must use a supported evaluator-owned boundary"
                )
            if trigger == "after_artifacts_committed":
                prerequisites = event.get("after_artifacts")
                if not isinstance(prerequisites, list) or not prerequisites:
                    errors.append(f"{prefix} after_artifacts must be a non-empty list")
                else:
                    unknown_prerequisites = set(prerequisites) - artifacts
                    if unknown_prerequisites:
                        errors.append(
                            f"{prefix} after_artifacts references unknown artifacts "
                            f"{sorted(unknown_prerequisites)!r}"
                        )
            if trigger == "after_results_delivered":
                prerequisites = event.get("after_results")
                if not isinstance(prerequisites, list) or not prerequisites:
                    errors.append(f"{prefix} after_results must be a non-empty list")
                else:
                    unknown_results = set(map(str, prerequisites)) - allowed
                    if unknown_results:
                        errors.append(
                            f"{prefix} after_results references unknown result roles "
                            f"{sorted(unknown_results)!r}"
                        )
                    if str(result) in set(map(str, prerequisites)):
                        errors.append(f"{prefix} cannot wait for its own result role")
        if event_type in WORKSTREAM_EVENT_TYPES:
            if str(event.get("workstream_id") or "") not in workstreams:
                errors.append(f"{prefix} references an unknown workstream_id")
        if event_type in REVISION_EVENT_TYPES and not (
            list(event.get("invalidates_artifacts") or [])
            or list(event.get("reopens_milestones") or [])
        ):
            errors.append(f"{prefix} revision event must invalidate or reopen observable state")
        unknown_artifacts = set(event.get("invalidates_artifacts") or []) - artifacts
        if unknown_artifacts:
            errors.append(f"{prefix} invalidates unknown artifacts {sorted(unknown_artifacts)!r}")
        unknown_milestones = set(event.get("reopens_milestones") or []) - milestones
        if unknown_milestones:
            errors.append(f"{prefix} reopens unknown milestones {sorted(unknown_milestones)!r}")
        if event_type == "deadline_update":
            # A live deadline_update row must carry a numeric wall-clock target;
            # the seam reads it through float(), so reject empty / non-numeric
            # declarations here rather than letting the episode crash mid-run.
            deadline_wall = event.get("deadline_wall")
            if deadline_wall is None:
                errors.append(f"{prefix} deadline_update must declare a numeric deadline_wall")
            else:
                try:
                    float(deadline_wall)
                except (TypeError, ValueError):
                    errors.append(
                        f"{prefix} deadline_update deadline_wall must be numeric, "
                        f"not {deadline_wall!r}"
                    )
    duplicates = sorted(
        result for result, count in Counter(result_events).items() if count > 1
    )
    if duplicates:
        errors.append(
            f"{execution_mode} schedules result kinds more than once {duplicates!r}; "
            "use completion_replay for an evaluator-owned replay"
        )
    scheduled_results = set(result_events)
    for event_id, replay_of in replay_events:
        if replay_of and replay_of not in scheduled_results:
            errors.append(
                f"{execution_mode} replay event {event_id!r} has no scheduled source result "
                f"{replay_of!r}"
            )
    return errors


def build_event_theme_fixtures() -> dict[str, dict[str, Any]]:
    """Return minimal private fixtures used to prove all eight themes are expressible."""
    common = {"invalidates_artifacts": [], "reopens_milestones": []}
    return {
        "delayed_authoritative_result": {
            "classification": {"primary_event_theme": "delayed_authoritative_result", "secondary_event_themes": [], "async_scenario_class": "result_eventful"},
            "events": [{"id": "provisional", "result": "provisional", **common}, {"id": "authority", "result": "authority", "invalidates_artifacts": ["final"], "reopens_milestones": ["integrate"]}],
        },
        "late_or_out_of_order_superseded_result": {
            "classification": {"primary_event_theme": "late_or_out_of_order_superseded_result", "secondary_event_themes": [], "async_scenario_class": "result_eventful"},
            "events": [{"id": "authority", "result": "authority", **common}, {"id": "late", "result": "provisional", **common}],
        },
        "partial_then_complete_result": {
            "classification": {"primary_event_theme": "partial_then_complete_result", "secondary_event_themes": [], "async_scenario_class": "result_eventful"},
            "events": [{"id": "partial", "result": "provisional", **common}, {"id": "complete", "result": "authority", "invalidates_artifacts": ["final"], "reopens_milestones": ["integrate"]}],
        },
        "conflicting_valid_results": {
            "classification": {"primary_event_theme": "conflicting_valid_results", "secondary_event_themes": [], "async_scenario_class": "result_eventful"},
            "events": [{"id": "left", "result": "provisional", **common}, {"id": "right", "result": "authority", **common}],
        },
        "duplicate_or_replayed_completion": {
            "classification": {"primary_event_theme": "duplicate_or_replayed_completion", "secondary_event_themes": [], "async_scenario_class": "result_eventful"},
            "events": [{"id": "original", "result": "authority", **common}, {"id": "replay", "stimulus_type": "completion_replay", "replay_of_result": "authority", "trigger": "after_consumed"}],
        },
        "child_failure_or_implicit_error": {
            "classification": {"primary_event_theme": "child_failure_or_implicit_error", "secondary_event_themes": [], "async_scenario_class": "resource_eventful"},
            "events": [{"id": "timeout", "stimulus_type": "child_timeout", "workstream_id": "provisional_stream"}],
        },
        "task_scope_or_dependency_change": {
            "classification": {"primary_event_theme": "task_scope_or_dependency_change", "secondary_event_themes": [], "async_scenario_class": "live_eventful"},
            "events": [{"id": "scope", "stimulus_type": "task_scope_revision", "invalidates_artifacts": ["final"], "reopens_milestones": ["integrate"]}],
        },
        "straggler_under_resource_pressure": {
            "classification": {"primary_event_theme": "straggler_under_resource_pressure", "secondary_event_themes": [], "async_scenario_class": "resource_eventful"},
            "events": [{"id": "pressure", "stimulus_type": "resource_pressure", "workstream_id": "provisional_stream", "resource": "concurrency_slot", "limit": 1}],
        },
    }


def validate_event_theme_fixtures() -> list[str]:
    errors: list[str] = []
    fixtures = build_event_theme_fixtures()
    if set(fixtures) != EVENT_THEME_IDS:
        errors.append("event theme fixtures must cover all eight registered themes exactly")
    for theme_id, fixture in fixtures.items():
        errors.extend(
            f"{theme_id}: {error}"
            for error in validate_case_classification(fixture.get("classification"))
        )
        errors.extend(
            f"{theme_id}: {error}"
            for error in validate_scenario_events(
                fixture.get("events"), execution_mode="async",
                allowed_results={"provisional", "authority"},
                workstream_ids={"provisional_stream", "authority_stream"},
                known_artifacts={"final"}, known_milestones={"integrate"},
            )
        )
    return errors
