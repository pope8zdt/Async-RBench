"""Evaluator-owned workspace observation and provisional-boundary detection.

The observer is evaluator-owned. It runs *after* a modifying main tool has
*completed*, captures a canonical snapshot of the evaluator-observable main
workspace, and — only when the state actually satisfies the case's provisional
predicate and the case declares at least one decision-bearing observation point —
records a ``provisional_observed`` kernel-private fact (spec §4).

It deliberately does not depend on ``artifact_committed``: a participant commit
may add lineage metadata, but it is not the boundary that creates a scored
opportunity (spec §4.3). The boundary is a completed, modify-tool-executed,
evaluator-observable state with a canonical digest.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Sequence

from .protocol import canonical_digest


# Tools whose completion can establish a provisional boundary. They are the only
# tools that carry a real task-relevant modification into the main workspace;
# read/query tools and the participant-visible ``commit_artifact`` audit signal
# are deliberately excluded (spec §4.1(1), §4.3).
MODIFYING_TOOLS = frozenset({"terminal", "promote_child_path"})


# A snapshot provider captures the evaluator-observable workspace state. It is
# injected per-domain so a Test can read a ``tmp_path`` marker while the runner
# closes over a real ``WorkspaceRuntime``. It returns the observed points plus
# any points that could not be observed.
SnapshotProvider = Callable[
    [Sequence["ObservationPoint"]], Awaitable["WorkspaceSnapshot"]
]


@dataclass(frozen=True)
class ObservationPoint:
    """One evaluator-defined point in the main workspace to observe.

    ``kind`` selects the canonicalisation: ``file`` and ``dir`` digest the raw
    filesystem bytes; ``json`` applies ``filter_path`` (a dot-path into the JSON
    document) and re-serialises a stable sub-value; ``command`` runs an
    evaluator-owned observer command and captures its stdout.
    """

    point_id: str
    kind: str
    path: str = ""
    filter_path: str | None = None
    command: str = ""

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> "ObservationPoint":
        return cls(
            point_id=str(spec.get("point_id") or spec.get("id") or ""),
            kind=str(spec.get("kind") or "file"),
            path=str(spec.get("path") or ""),
            filter_path=spec.get("filter_path"),
            command=str(spec.get("command") or ""),
        )


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """A canonicalised, evaluator-observable snapshot of the main workspace.

    ``points`` maps each observed point id to its canonical string value.
    ``missing_points`` names points that could not be observed (missing file,
    non-zero exit); ``error`` carries an observation-level failure. A snapshot
    is ``complete`` only when nothing was missing and no error occurred; an
    incomplete snapshot can never establish a provisional boundary (§4.1(3)).
    """

    points: Mapping[str, str] = field(default_factory=dict)
    missing_points: tuple[str, ...] = ()
    error: str | None = None

    @property
    def complete(self) -> bool:
        return self.error is None and not self.missing_points

    @property
    def digest(self) -> str:
        """Canonical digest of the observed points (spec §4.1(6))."""
        return canonical_digest(sorted(self.points.items()))


@dataclass(frozen=True)
class ProvisionalObservation:
    """Outcome of evaluating one observer trigger (started/finished event)."""

    established: bool = False
    digest: str | None = None
    action_id: str | None = None
    reason: str | None = None
    points: Mapping[str, str] = field(default_factory=dict)

    @property
    def provisional_established(self) -> bool:
        return self.established

    def to_fact(self) -> dict[str, Any]:
        """The kernel-private event-source fact for this observation."""
        return {
            "type": "provisional_observed",
            "provisional_established": self.established,
            "provisional_digest": self.digest,
            "action_id": self.action_id,
            "reason": self.reason,
            "observed_points": dict(self.points),
        }


def canonicalize_point_value(kind: str, value: Any) -> str:
    """Canonicalise one observed point value into a stable string.

    Lists (directory listings or multi-line command output) are sorted and
    joined so the resulting digest is insensitive to read ordering. JSON values
    are re-serialised with sorted keys so key order never changes the digest.
    """
    if kind == "json":
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "\n".join(sorted(str(item) for item in value))
    return str(value)


def snapshot_observation_command(point: ObservationPoint) -> str:
    """Build the evaluator-owned shell command that observes one point.

    For ``command`` points this is the case's observer command. For ``file``,
    ``dir`` and ``json`` points the kernel synthesises a self-contained one-liner
    that prints a canonical value. The command never receives an adapter-supplied
    argument beyond the declared point path, and its output is kept
    kernel-private in the ``provisional_observed`` event.
    """
    if point.kind == "command":
        return point.command
    if point.kind == "json":
        script = (
            "import json,pathlib,sys,sys\n"
            "p=pathlib.Path(sys.argv[1]);\n"
            "assert p.exists(), f'missing:{p}';\n"
            "doc=json.loads(p.read_text(encoding='utf-8'));\n"
            "val=doc\n"
            "parts=[s for s in sys.argv[2].split('.') if s] if len(sys.argv)>2 else []\n"
            "for key in parts:\n"
            "    val=val[int(key)] if (isinstance(val,list) and key.isdigit()) else val[key]\n"
            "print(json.dumps(val, sort_keys=True, separators=(',',':'), ensure_ascii=False))\n"
        )
        return (
            f"python -c {shlex.quote(script)} "
            f"{shlex.quote(point.path)} {shlex.quote(point.filter_path or '')}"
        )
    if point.kind == "file":
        script = (
            "import hashlib,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
            "assert p.exists(), f'missing:{p}'; print(hashlib.sha256(p.read_bytes()).hexdigest())"
        )
        return f"python -c {shlex.quote(script)} {shlex.quote(point.path)}"
    if point.kind == "dir":
        script = (
            "import hashlib,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
            "assert p.exists(), f'missing:{p}'; h=hashlib.sha256(); "
            "files=sorted(q for q in p.rglob('*') if q.is_file()); "
            "[(h.update(q.relative_to(p).as_posix().encode()), h.update(b'\\0'), "
            "h.update(q.read_bytes()), h.update(b'\\0')) for q in files]; print(h.hexdigest())"
        )
        return f"python -c {shlex.quote(script)} {shlex.quote(point.path)}"
    raise ValueError(f"unsupported observation point kind: {point.kind!r}")


def parse_observation_output(point: ObservationPoint, output: str) -> str:
    """Extract a canonical value from an observer command's stdout.

    The last non-empty line is used for scalar/command output (matching the
    existing artifact observer), so a noisy command still yields the value the
    case expects while an empty output fails as unobservable.
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1]


class ProvisionalObserver:
    """Decides whether a provisional boundary is established.

    A provisional boundary requires, in order (spec §4.1):
      1. a stored ``main_action_started`` for a modifying tool,
      2. its ``main_action_finished`` with success,
      3. an evaluator-observable, complete workspace snapshot,
      4. the case's provisional predicate satisfied.

    An established boundary is sticky for the rest of the episode: once the
    evaluator observes a valid provisional state, later non-modifying events do
    not retract it.
    """

    def __init__(
        self,
        points: Sequence[ObservationPoint] | None = None,
        *,
        predicate: Mapping[str, Any] | None = None,
        snapshot_provider: SnapshotProvider | None = None,
        modifying_tools: frozenset[str] | None = None,
    ) -> None:
        self._points = list(points or [])
        self._predicate = dict(predicate or {})
        self._snapshot_provider = snapshot_provider
        self._modifying_tools = modifying_tools if modifying_tools is not None else MODIFYING_TOOLS
        self._in_progress: tuple[str, str] | None = None
        self._established = False
        self._established_digest: str | None = None

    @property
    def established(self) -> bool:
        return self._established

    @property
    def established_digest(self) -> str | None:
        return self._established_digest

    @property
    def points(self) -> list[ObservationPoint]:
        return list(self._points)

    async def observe_snapshot(self) -> WorkspaceSnapshot:
        """Capture the current workspace snapshot through the injected provider."""
        if self._snapshot_provider is not None:
            return await self._snapshot_provider(self._points)
        return WorkspaceSnapshot(points={})

    async def observe(self, *, action_id: str | None = None) -> ProvisionalObservation:
        """Capture the workspace and evaluate the provisional predicate now.

        This is the evaluator-owned trigger used by the runner when the adapter
        reports a completed modifying tool. It does not itself decide whether the
        completion was legitimate — the adapter only calls it after a modifying
        tool finishes — but it does require a complete, predicate-satisfying
        snapshot before asserting a boundary (§4.1(3), §4.1(4)).
        """
        snapshot = await self.observe_snapshot()
        if not snapshot.complete:
            return ProvisionalObservation(
                established=False, action_id=action_id,
                reason=snapshot.error or "incomplete_snapshot",
            )
        if not self._satisfies_predicate(snapshot):
            return ProvisionalObservation(
                established=False, action_id=action_id, reason="predicate_not_met",
            )
        self._established = True
        self._established_digest = snapshot.digest
        return ProvisionalObservation(
            established=True, digest=snapshot.digest, action_id=action_id,
            points=dict(snapshot.points),
        )

    async def on_event(self, event: Mapping[str, Any]) -> ProvisionalObservation:
        """Evaluate one main-action lifecycle event against the boundary.

        ``main_action_started`` only records an in-progress modifying tool; it
        can never establish provisional. ``main_action_finished`` captures the
        snapshot and establishes provisional when all §4.1 conditions hold.
        """
        event_type = event.get("type")
        action_id = str(event.get("action_id") or "")
        if event_type == "main_action_started":
            self._in_progress = (action_id, str(event.get("kind") or ""))
            return ProvisionalObservation(
                established=False, action_id=action_id,
                reason="tool_still_running",
            )
        if event_type != "main_action_finished":
            return ProvisionalObservation(established=False, action_id=action_id)
        if self._in_progress is None or self._in_progress[0] != action_id:
            return ProvisionalObservation(
                established=False, action_id=action_id, reason="unmatched_start",
            )
        started_kind = self._in_progress[1]
        self._in_progress = None
        if not bool(event.get("success", True)):
            return ProvisionalObservation(
                established=False, action_id=action_id, reason="tool_failed",
            )
        if started_kind not in self._modifying_tools:
            return ProvisionalObservation(
                established=False, action_id=action_id, reason="non_modifying_tool",
            )
        return await self.observe(action_id=action_id)

    def _satisfies_predicate(self, snapshot: WorkspaceSnapshot) -> bool:
        """A predicate declares required points or a decision-bearing point.

        With no predicate declared the boundary is established once the
        snapshot is complete (a modifying tool completed and the evaluator can
        observe stable state) — the decision-bearing requirement is satisfied by
        the existence of the observed points themselves.
        """
        required = self._predicate.get("required_points")
        if required is not None:
            needed = {str(item) for item in required}
            if not needed.issubset(set(snapshot.points)):
                return False
        if self._predicate.get("any_point"):
            return bool(snapshot.points)
        return True

    def to_fact(self, observation: ProvisionalObservation) -> dict[str, Any]:
        return observation.to_fact()
