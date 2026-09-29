from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .evaluation.case_bundle import public_case_bundle_sha256
from .evaluation.event_taxonomy import EVENT_THEME_IDS


PAPER_RELEASE_ID = "v11.0-paper"
PAPER_SOURCES = (
    "terminal-bench",
    "gaia2",
    "osworld",
    "swe-bench",
    "multiagentbench",
)


def normalize_release_source(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "multiagent-bench": "multiagentbench",
        "multiagentbench": "multiagentbench",
        "swebench": "swe-bench",
        "swe-bench": "swe-bench",
        "terminalbench": "terminal-bench",
        "terminal-bench": "terminal-bench",
        "os-world": "osworld",
        "osworld": "osworld",
        "gaia-2": "gaia2",
        "gaia2": "gaia2",
    }
    return aliases.get(normalized, normalized)


@dataclass(frozen=True)
class CorpusStats:
    case_count: int
    source_counts: dict[str, int]
    difficulty_counts: dict[str, int]
    initial_subtask_count: int
    subtask_histogram: dict[str, int]

    @classmethod
    def from_case_rows(cls, rows: Iterable[Mapping[str, Any]]) -> "CorpusStats":
        selected = list(rows)
        sources = Counter(normalize_release_source(row.get("source")) for row in selected)
        difficulties = Counter(str(row.get("difficulty") or "").strip().lower() for row in selected)
        subtask_counts = [int(row.get("initial_subtasks") or 0) for row in selected]
        histogram = {
            "2": sum(value == 2 for value in subtask_counts),
            "3": sum(value == 3 for value in subtask_counts),
            "4_plus": sum(value >= 4 for value in subtask_counts),
        }
        return cls(
            case_count=len(selected),
            source_counts=dict(sorted(sources.items())),
            difficulty_counts=dict(sorted(difficulties.items())),
            initial_subtask_count=sum(subtask_counts),
            subtask_histogram=histogram,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_count": self.case_count,
            "source_counts": dict(self.source_counts),
            "difficulty_counts": dict(self.difficulty_counts),
            "initial_subtask_count": self.initial_subtask_count,
            "subtask_histogram": dict(self.subtask_histogram),
        }


@dataclass(frozen=True)
class PublicReleaseManifest:
    release_id: str
    registry_sha256: str
    cases: tuple[Mapping[str, Any], ...]
    stats: CorpusStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "release_id": self.release_id,
            "registry_sha256": self.registry_sha256,
            "stats": self.stats.to_dict(),
            "cases": [dict(row) for row in sorted(self.cases, key=lambda row: str(row["case_id"]))],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class JudgeReleaseManifest:
    release_id: str
    public_release_sha256: str
    cases: tuple[Mapping[str, Any], ...]
    scenario_counts: dict[str, int]
    target_event_count: int

    @classmethod
    def from_cases(
        cls,
        public_release: PublicReleaseManifest,
        cases: Iterable[Mapping[str, Any]],
    ) -> "JudgeReleaseManifest":
        selected = tuple(sorted((dict(row) for row in cases), key=lambda row: str(row["case_id"])))
        return cls(
            release_id=public_release.release_id,
            public_release_sha256=_canonical_sha256(public_release.to_dict()),
            cases=selected,
            scenario_counts=dict(sorted(Counter(str(row.get("scenario") or "") for row in selected).items())),
            target_event_count=sum(int(row.get("target_event_count") or 0) for row in selected),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "release_id": self.release_id,
            "public_release_sha256": self.public_release_sha256,
            "scenario_counts": dict(self.scenario_counts),
            "target_event_count": self.target_event_count,
            "cases": [dict(row) for row in self.cases],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _expect(errors: list[str], label: str, actual: int, expected: int) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected}, got {actual}")


def validate_paper_invariants(
    public_release: PublicReleaseManifest,
    judge_release: Mapping[str, Any] | None = None,
) -> list[str]:
    stats = public_release.stats
    errors: list[str] = []
    _expect(errors, "case_count", stats.case_count, 200)
    for source in PAPER_SOURCES:
        _expect(errors, f"source_counts.{source}", stats.source_counts.get(source, 0), 40)
    unknown_sources = sorted(set(stats.source_counts) - set(PAPER_SOURCES))
    if unknown_sources:
        errors.append("source_counts: unsupported sources: " + ", ".join(unknown_sources))
    _expect(errors, "difficulty_counts.medium", stats.difficulty_counts.get("medium", 0), 104)
    _expect(errors, "difficulty_counts.hard", stats.difficulty_counts.get("hard", 0), 96)
    _expect(errors, "initial_subtask_count", stats.initial_subtask_count, 621)
    _expect(errors, "subtask_histogram.2", stats.subtask_histogram.get("2", 0), 73)
    _expect(errors, "subtask_histogram.3", stats.subtask_histogram.get("3", 0), 40)
    _expect(errors, "subtask_histogram.4_plus", stats.subtask_histogram.get("4_plus", 0), 87)
    if judge_release is not None:
        scenario_counts = dict(judge_release.get("scenario_counts") or {})
        for scenario in sorted(EVENT_THEME_IDS):
            _expect(errors, f"scenario_counts.{scenario}", int(scenario_counts.get(scenario, 0)), 25)
        unknown = sorted(set(scenario_counts) - set(EVENT_THEME_IDS))
        if unknown:
            errors.append("scenario_counts: unsupported scenarios: " + ", ".join(unknown))
    return errors


def validate_paired_release(
    public_release: PublicReleaseManifest,
    judge_release: JudgeReleaseManifest,
) -> list[str]:
    errors = validate_paper_invariants(public_release, judge_release.to_dict())
    if judge_release.release_id != public_release.release_id:
        errors.append("release_id: public and judge manifests differ")
    expected_public_sha = _canonical_sha256(public_release.to_dict())
    if judge_release.public_release_sha256 != expected_public_sha:
        errors.append("public_release_sha256: judge manifest does not bind this public release")
    public_by_id = {str(row["case_id"]): row for row in public_release.cases}
    judge_by_id = {str(row["case_id"]): row for row in judge_release.cases}
    if set(public_by_id) != set(judge_by_id):
        errors.append("case_ids: public and judge manifests differ")
    for case_id in sorted(set(public_by_id) & set(judge_by_id)):
        if judge_by_id[case_id].get("public_bundle_sha256") != public_by_id[case_id].get("public_bundle_sha256"):
            errors.append(f"{case_id}: public bundle digest mismatch")
        if int(judge_by_id[case_id].get("target_event_count") or 0) != 1:
            errors.append(f"{case_id}: expected exactly one target event")
    _expect(errors, "target_event_count", judge_release.target_event_count, 200)
    return errors


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_public_release(root: Path, *, release_id: str = PAPER_RELEASE_ID) -> PublicReleaseManifest:
    root = root.resolve()
    registry_path = root / "data" / "async-rbench" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    cases_root = registry_path.parent / "cases"
    rows: list[dict[str, Any]] = []
    for registered in registry.get("case_families") or []:
        case_id = str(registered["case_id"])
        case_dir = cases_root / case_id
        public = yaml.safe_load((case_dir / "public" / "case.yaml").read_text(encoding="utf-8"))
        task = yaml.safe_load((case_dir / "task" / "task.yaml").read_text(encoding="utf-8"))
        source = normalize_release_source((public.get("source_tasks") or [{}])[0].get("benchmark"))
        rows.append({
            "case_id": case_id,
            "source": source,
            "difficulty": str((task or {}).get("difficulty") or "").lower(),
            "initial_subtasks": len(public.get("workstreams") or []),
            "public_bundle_sha256": public_case_bundle_sha256(case_dir),
        })
    rows.sort(key=lambda row: row["case_id"])
    return PublicReleaseManifest(
        release_id=release_id,
        registry_sha256=_sha256(registry_path),
        cases=tuple(rows),
        stats=CorpusStats.from_case_rows(rows),
    )


def _judge_case_bundle_sha256(case_dir: Path) -> str:
    digest = hashlib.sha256()
    files = [
        path for path in case_dir.rglob("*")
        if path.is_file() and path.name != "STATUS.json" and "__pycache__" not in path.parts
    ]
    for path in sorted(files, key=lambda item: item.relative_to(case_dir).as_posix()):
        relative = path.relative_to(case_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_judge_release(
    root: Path,
    judge_root: Path,
    public_release: PublicReleaseManifest | None = None,
) -> JudgeReleaseManifest:
    public_release = public_release or build_public_release(root)
    public_by_id = {str(row["case_id"]): row for row in public_release.cases}
    rows: list[dict[str, Any]] = []
    for case_id in sorted(public_by_id):
        case_dir = judge_root.resolve() / "cases" / case_id
        private_path = case_dir / "evaluator" / "case.yaml"
        private = yaml.safe_load(private_path.read_text(encoding="utf-8"))
        if not isinstance(private, dict):
            raise ValueError(f"private case contract must be a mapping: {private_path}")
        scenario = str((private.get("classification") or {}).get("primary_event_theme") or "")
        # Pre-v11 bundles did not serialize ``event_status``. Their sole
        # event_contract is nevertheless the registered scoring target; the
        # seven original pilot bundles predate event_contracts entirely and
        # identify that same single target through authoritative_result_kind.
        contracts = list(private.get("event_contracts") or [])
        target_count = len(contracts) if contracts else int(bool(private.get("authoritative_result_kind")))
        rows.append({
            "case_id": case_id,
            "scenario": scenario,
            "target_event_count": target_count,
            "public_bundle_sha256": public_by_id[case_id]["public_bundle_sha256"],
            "judge_bundle_sha256": _judge_case_bundle_sha256(case_dir),
        })
    return JudgeReleaseManifest.from_cases(public_release, rows)
