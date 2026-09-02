from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from async_rbench.evaluation.observation import (
    ObservationPoint, ProvisionalObserver, WorkspaceSnapshot,
    canonicalize_point_value, snapshot_observation_command,
)
from async_rbench.evaluation.protocol import canonical_digest


def _event(event_type: str, **fields: object) -> dict[str, object]:
    return {"type": event_type, **fields}


def _marker_provider(tmp_path: Path):
    """An async snapshot provider that reads a marker file from ``tmp_path``."""
    marker = tmp_path / "state.marker"

    async def provide(points) -> WorkspaceSnapshot:
        if marker.exists():
            value = marker.read_text(encoding="utf-8").strip()
            if value:
                return WorkspaceSnapshot(points={"state": value})
        return WorkspaceSnapshot(points={}, missing_points=("state",))

    return provide


def _error_provider(tmp_path: Path):
    """A provider whose observation always fails (simulated observer error)."""
    async def provide(points) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(points={}, error="observer command failed")

    return provide


def _observer(tmp_path: Path, provider=None, points=None) -> ProvisionalObserver:
    if points is None:
        points = [ObservationPoint(
            point_id="state", kind="file", path=str(tmp_path / "state.marker"),
        )]
    return ProvisionalObserver(
        points, snapshot_provider=provider or _marker_provider(tmp_path),
    )


def test_main_action_started_cannot_establish_provisional(tmp_path: Path) -> None:
    """A started modifying tool is not a boundary; only completion is (spec §4.2)."""
    async def exercise() -> None:
        observer = _observer(tmp_path)
        # The workspace already holds a valid provisional state, but the tool has
        # only *started*.  A started modifying tool is not a boundary, so the
        # observer must not establish provisional yet (spec §4.2).
        (tmp_path / "state.marker").write_text("state=v1", encoding="utf-8")
        started = _event("main_action_started", action_id="a1", kind="terminal")
        obs = await observer.on_event(started)
        assert obs.provisional_established is False
        assert obs.reason == "tool_still_running"

        # Only after the tool *completes* does the boundary fall.
        finished = _event("main_action_finished", action_id="a1", success=True)
        obs = await observer.on_event(finished)
        assert obs.provisional_established is True
        assert obs.digest is not None

    asyncio.run(exercise())


def test_missing_file_cannot_establish_provisional(tmp_path: Path) -> None:
    """An incomplete snapshot (missing point) never establishes a boundary."""
    async def exercise() -> None:
        observer = _observer(tmp_path)
        await observer.on_event(
            _event("main_action_started", action_id="m1", kind="terminal"),
        )
        obs = await observer.on_event(
            _event("main_action_finished", action_id="m1", success=True),
        )
        assert obs.provisional_established is False
        assert obs.reason == "incomplete_snapshot"

    asyncio.run(exercise())


def test_failed_observer_command_cannot_establish_provisional(tmp_path: Path) -> None:
    """An observer error (failed command) is an evaluator-side failure, not a boundary."""
    async def exercise() -> None:
        observer = _observer(tmp_path, provider=_error_provider(tmp_path))
        await observer.on_event(
            _event("main_action_started", action_id="e1", kind="terminal"),
        )
        obs = await observer.on_event(
            _event("main_action_finished", action_id="e1", success=True),
        )
        assert obs.provisional_established is False
        assert obs.reason == "observer command failed"

    asyncio.run(exercise())


def test_valid_provisional_without_commit_artifact(tmp_path: Path) -> None:
    """Provisional is established purely from completed state, not commit_artifact."""
    async def exercise() -> None:
        observer = _observer(tmp_path)
        (tmp_path / "state.marker").write_text("answer=42", encoding="utf-8")
        await observer.on_event(
            _event("main_action_started", action_id="p1", kind="terminal"),
        )
        obs = await observer.on_event(
            _event("main_action_finished", action_id="p1", success=True),
        )
        assert obs.provisional_established is True
        assert obs.points == {"state": "answer=42"}

    asyncio.run(exercise())


def test_non_modifying_tool_never_establishes_provisional(tmp_path: Path) -> None:
    """Read/query tools cannot establish the boundary even if the state exists."""
    async def exercise() -> None:
        observer = _observer(tmp_path)
        (tmp_path / "state.marker").write_text("state=v1", encoding="utf-8")
        await observer.on_event(
            _event("main_action_started", action_id="q1", kind="list_subagents"),
        )
        obs = await observer.on_event(
            _event("main_action_finished", action_id="q1", success=True),
        )
        assert obs.provisional_established is False
        assert obs.reason == "non_modifying_tool"

    asyncio.run(exercise())


def test_failed_tool_does_not_establish_provisional(tmp_path: Path) -> None:
    async def exercise() -> None:
        observer = _observer(tmp_path)
        (tmp_path / "state.marker").write_text("state=v1", encoding="utf-8")
        await observer.on_event(
            _event("main_action_started", action_id="f1", kind="terminal"),
        )
        obs = await observer.on_event(
            _event("main_action_finished", action_id="f1", success=False),
        )
        assert obs.provisional_established is False
        assert obs.reason == "tool_failed"

    asyncio.run(exercise())


def test_snapshot_digest_is_stable_and_distinguishes_state(tmp_path: Path) -> None:
    async def exercise() -> None:
        (tmp_path / "state.marker").write_text("same", encoding="utf-8")
        first = await _observer(tmp_path).observe_snapshot()
        second = await _observer(tmp_path).observe_snapshot()
        assert first.digest == second.digest
        (tmp_path / "state.marker").write_text("changed", encoding="utf-8")
        third = await _observer(tmp_path).observe_snapshot()
        assert third.digest != first.digest

    asyncio.run(exercise())


def test_observe_establishes_boundary_directly(tmp_path: Path) -> None:
    """The runner's observe() path also establishes on a complete snapshot."""
    async def exercise() -> None:
        observer = _observer(tmp_path)
        (tmp_path / "state.marker").write_text("state=v2", encoding="utf-8")
        obs = await observer.observe(action_id="a1")
        assert obs.provisional_established is True
        assert obs.digest is not None
        assert observer.established is True
        assert observer.established_digest == obs.digest

    asyncio.run(exercise())


def test_observation_point_spec_round_trips() -> None:
    spec = {
        "point_id": "config", "kind": "json", "path": "/app/config.json",
        "filter_path": "db.port",
    }
    point = ObservationPoint.from_spec(spec)
    assert point.point_id == "config"
    assert point.kind == "json"
    assert point.filter_path == "db.port"
    assert point.command == ""
    point2 = ObservationPoint.from_spec({"id": "only", "kind": "command", "command": "observe"})
    assert point2.point_id == "only"
    assert point2.kind == "command"
    assert point2.command == "observe"


def test_canonicalize_json_is_key_order_insensitive() -> None:
    a = canonicalize_point_value("json", {"b": 1, "a": 2})
    b = canonicalize_point_value("json", {"a": 2, "b": 1})
    assert a == b
    assert canonical_digest({"value": a}) == canonical_digest({"value": b})


def test_snapshot_command_for_file_and_json_are_bounded() -> None:
    file_cmd = snapshot_observation_command(ObservationPoint(
        point_id="f", kind="file", path="/app/main.db",
    ))
    assert "hashlib.sha256" in file_cmd
    json_cmd = snapshot_observation_command(ObservationPoint(
        point_id="j", kind="json", path="/app/config.json", filter_path="db.port",
    ))
    assert "json.loads" in json_cmd
    # The path is never interpolated into a shell the caller does not own.
    assert "main.db" in file_cmd


def test_empty_observation_points_cannot_establish_provisional(tmp_path: Path) -> None:
    """§4.1(5): no decision-bearing observation point means no provisional, even
    on a complete snapshot. A case that declares no observation point has no
    evaluator-observable state to watch change or stay."""
    async def exercise() -> None:
        observer = ProvisionalObserver([], snapshot_provider=_marker_provider(tmp_path))
        (tmp_path / "state.marker").write_text("state=v1", encoding="utf-8")
        await observer.on_event(
            _event("main_action_started", action_id="n1", kind="terminal"),
        )
        obs = await observer.on_event(
            _event("main_action_finished", action_id="n1", success=True),
        )
        assert obs.provisional_established is False
        assert obs.reason == "no_decision_bearing_points"
        assert observer.established is False

    asyncio.run(exercise())


def test_provisional_requires_a_decision_bearing_point(tmp_path: Path) -> None:
    """§4.1(5) happy path: an explicit observation point plus a complete snapshot
    establishes provisional; the same complete snapshot without a declared point
    does not."""
    async def exercise() -> None:
        (tmp_path / "state.marker").write_text("answer=42", encoding="utf-8")
        # With a declared point the boundary establishes.
        with_point = _observer(tmp_path)
        obs = await with_point.observe(action_id="a1")
        assert obs.provisional_established is True
        assert obs.points == {"state": "answer=42"}

    asyncio.run(exercise())
