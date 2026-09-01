"""Source provenance validation across all Async-RBench benchmark families.

Each benchmark source family has its own lock file under upstream/<benchmark>/:
  terminal-bench  upstream/terminal-bench/SOURCE_LOCK.json  {source_root, commit, tasks:{task_id: tree_sha256}}
  gaia2           upstream/gaia2/SOURCE_LOCK.json           {source_url, commit, scenarios:{scenario_id: sha256}}
  swe-bench       upstream/swe-bench/SOURCE_LOCK.json       {source_url, commit, instances:{instance_id: sha256}}
  gaia            gated; validated only as blocked_access_review (no lock needed)

A public/private case contract's source_tasks entry selects its family with ``benchmark`` and is
validated against that family's lock. Terminal-Bench cases additionally keep
the byte-identical preserved-test / upstream-solution checks.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .spec import normalize_case_benchmark


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(path: Path) -> str:
    lines = []
    for item in sorted(
        (
            p for p in path.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        ),
        key=lambda p: p.relative_to(path).as_posix().lower(),
    ):
        lines.append(f"{item.relative_to(path).as_posix()} {file_sha256(item)}")
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def same_asset(left: Path, right: Path) -> bool:
    if left.is_file() and right.is_file():
        return file_sha256(left) == file_sha256(right)
    if left.is_dir() and right.is_dir():
        return tree_sha256(left) == tree_sha256(right)
    return False


SUPPORTED_IMPLEMENTATIONS = ("real-instance-derived", "structure-derived", "blocked-access-review")
SUPPORTED_BENCHMARKS = (
    "terminal-bench", "gaia2", "swe-bench", "gaia", "multiagentbench", "osworld",
)
LOCK_PATHS = {
    "terminal-bench": "upstream/terminal-bench/SOURCE_LOCK.json",
    "gaia2": "upstream/gaia2/SOURCE_LOCK.json",
    "swe-bench": "upstream/swe-bench/SOURCE_LOCK.json",
    "gaia": None,  # gated; no lock is expected
    # These families use a per-case source_lock.json because their source
    # records span many native files rather than one collection-wide hash map.
    "multiagentbench": None,
    "osworld": None,
}
GATED_BENCHMARKS = {"gaia"}
SOURCE_NATIVE_BENCHMARKS = {"multiagentbench", "osworld"}


def _load_lock(root: Path, benchmark: str) -> tuple[dict | None, str | None]:
    rel = LOCK_PATHS[benchmark]
    if rel is None:
        return None, None
    lock_path = root / rel
    if not lock_path.is_file():
        return None, f"missing source lock for {benchmark}: {lock_path}"
    try:
        return json.loads(lock_path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"invalid source lock {lock_path}: {exc}"


def _validate_terminal_bench_task(root: Path, case, source, lock, errors: list[str]) -> None:
    commit = source.get("upstream_commit") or case.raw.get("upstream_commit")
    if commit and lock.get("commit") and commit != lock["commit"]:
        errors.append(f"{case.case_id}: upstream commit does not match terminal-bench source lock")
    task_id = str(source["id"])
    if task_id not in lock.get("tasks", {}):
        errors.append(f"{case.case_id}: unlocked source task {task_id}")
        return
    expected = lock["tasks"][task_id]
    upstream_root = root / "upstream/terminal-bench" / lock.get("source_root", "original-tasks-locked")
    task_dir = upstream_root / task_id
    actual = tree_sha256(task_dir) if task_dir.is_dir() else None
    if actual != expected:
        errors.append(f"{case.case_id}: upstream tree mismatch for {task_id}: expected {expected}, got {actual}")
    # Upstream tests are optional provenance material, not the Async-RBench outcome
    # contract. Cases may retain a byte-identical copy for audit, but the private
    # verifier uses case-specific dynamic-integration tests.
    if preserved_test_path := source.get("preserved_test"):
        upstream_test = root / source["upstream_path"] / "tests/test_outputs.py"
        preserved_test = case.case_dir / preserved_test_path
        if not same_asset(upstream_test, preserved_test):
            errors.append(f"{case.case_id}: preserved test differs for {task_id}")
    upstream_solution = root / source["upstream_path"] / "solution.sh"
    preserved_solution = case.case_dir / "task/upstream_solutions" / f"{task_id}.sh"
    if not same_asset(upstream_solution, preserved_solution):
        errors.append(f"{case.case_id}: preserved oracle differs for {task_id}")


def _validate_hash_locked_source(case, source, lock, id_key: str, errors: list[str]) -> None:
    """Validate a scenario/instance against a {id: sha256} lock entry."""
    source_id = str(source["id"])
    expected_map = lock.get(id_key, {})
    if source_id not in expected_map:
        errors.append(f"{case.case_id}: unlocked source {id_key} {source_id}")
        return
    expected_sha = expected_map[source_id]
    actual_sha = str(source.get("source_sha256") or "")
    if actual_sha and actual_sha != expected_sha:
        errors.append(f"{case.case_id}: source hash mismatch for {source_id}: expected {expected_sha}, got {actual_sha}")
    commit = source.get("upstream_commit") or case.raw.get("upstream_commit")
    if commit and lock.get("commit") and commit != lock["commit"]:
        errors.append(f"{case.case_id}: upstream commit does not match {id_key} source lock")


def _validate_source_native_lock(root: Path, case, source, errors: list[str]) -> None:
    lock_path = case.case_dir / "private" / "source_lock.json"
    if not lock_path.is_file():
        errors.append(f"{case.case_id}: missing per-case source-native lock {lock_path}")
        return
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"{case.case_id}: invalid source-native lock: {exc}")
        return
    source_files = list(lock.get("source_files") or [])
    expected = dict(lock.get("source_file_sha256") or {})
    if not source_files or set(source_files) != set(expected):
        errors.append(f"{case.case_id}: source-native lock files and hashes must match exactly")
        return
    for relative in source_files:
        # Prefer a case-contained source snapshot so the lock survives the
        # candidate_cases/ -> cases/ promotion move.  Shared immutable source
        # archives remain supported through the repository-root fallback.
        path = case.case_dir / relative
        if not path.is_file():
            path = root / relative
        if not path.is_file():
            errors.append(f"{case.case_id}: locked source file is missing: {relative}")
            continue
        actual = file_sha256(path)
        if actual != str(expected[relative]):
            errors.append(
                f"{case.case_id}: source-native hash mismatch for {relative}: "
                f"expected {expected[relative]}, got {actual}"
            )
    if not str(source.get("id") or "").strip():
        errors.append(f"{case.case_id}: source-native task id is empty")


def validate_relocatable_source_native_lock(case_dir: Path) -> list[str]:
    """Require a self-contained source lock that survives moving the case."""
    lock_path = case_dir / "private" / "source_lock.json"
    if not lock_path.is_file():
        return []
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [f"{case_dir.name}: invalid source-native lock: {exc}"]
    errors: list[str] = []
    for relative in list(lock.get("source_files") or []):
        source_path = Path(str(relative))
        parts = source_path.parts
        if (
            source_path.is_absolute()
            or ".." in parts
            or not parts
            or parts[0] != "private"
        ):
            errors.append(
                f"{case_dir.name}: source-native lock path must be case-relative under "
                f"private/: {relative}"
            )
            continue
        if not (case_dir / source_path).is_file():
            errors.append(
                f"{case_dir.name}: case-contained locked source file is missing: {relative}"
            )
    production = str(lock.get("production_case_path") or "")
    if production != ".":
        errors.append(
            f"{case_dir.name}: production_case_path must be '.': {production or '<missing>'}"
        )
    return errors


def validate_sources(root: Path, cases) -> list[str]:
    """Validate every case against its benchmark source lock(s)."""
    errors: list[str] = []
    for case in cases:
        implementation = case.raw.get("implementation")
        if implementation not in SUPPORTED_IMPLEMENTATIONS:
            errors.append(f"{case.case_id}: implementation {implementation!r} is unsupported")
        source_tasks = case.raw.get("source_tasks", [])
        if not source_tasks:
            errors.append(f"{case.case_id}: source_tasks is empty")
        for source in source_tasks:
            benchmark = normalize_case_benchmark(source.get("benchmark") or "terminal-bench")
            if benchmark not in SUPPORTED_BENCHMARKS:
                errors.append(f"{case.case_id}: unsupported source benchmark {benchmark!r}")
                continue
            if benchmark in GATED_BENCHMARKS:
                if implementation != "blocked-access-review":
                    errors.append(
                        f"{case.case_id}: gated source {source.get('id')} requires implementation=blocked-access-review"
                    )
                continue
            if benchmark in SOURCE_NATIVE_BENCHMARKS:
                if implementation == "blocked-access-review":
                    errors.append(
                        f"{case.case_id}: blocked-access-review must not reference a source-native task {source.get('id')}"
                    )
                else:
                    _validate_source_native_lock(root, case, source, errors)
                continue
            if implementation == "blocked-access-review":
                errors.append(
                    f"{case.case_id}: blocked-access-review must not reference a lockable source {source.get('id')}"
                )
                continue
            lock, lock_error = _load_lock(root, benchmark)
            if lock_error:
                errors.append(lock_error)
                continue
            if benchmark == "terminal-bench":
                _validate_terminal_bench_task(root, case, source, lock, errors)
            elif benchmark == "gaia2":
                _validate_hash_locked_source(case, source, lock, "scenarios", errors)
            elif benchmark == "swe-bench":
                _validate_hash_locked_source(case, source, lock, "instances", errors)
        for copy in case.raw.get("asset_copies", []):
            source = root / copy["from"]
            # ``to`` is resolved case-directory-relative first, so the same
            # The contract validates both as a candidate (candidate_cases/<id>/)
            # and after promotion (cases/<id>/); legacy root-relative paths
            # used by earlier official cases are still accepted as a fallback.
            target = case.case_dir / copy["to"]
            if not same_asset(source, target):
                target = root / copy["to"]
            if not same_asset(source, target):
                errors.append(f"{case.case_id}: copied asset differs: {copy['from']} -> {copy['to']}")
        workstream_ids = {str(item.get("id")) for item in case.raw.get("delegation_workstreams", [])}
        wave_ids = {str(item.get("workstream_id")) for item in case.raw.get("initial_wave", [])}
        if wave_ids != workstream_ids:
            errors.append(
                f"{case.case_id}: initial_wave must map one-to-one to delegation_workstreams ids"
            )
    return errors
