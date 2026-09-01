from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .evaluation.pytest_results import (
    parse_component_summaries, parse_pytest_summary, parse_semantic_check_results,
)


# These paths must not exist in an evaluated participant container. Keep the
# list explicit so the contamination audit fails closed when packaging regresses.
FORBIDDEN_PARTICIPANT_PATHS = (
    "/async_rbench-tests",
    "/async_rbench_tests",
    "/tests",
    "/async_rbench/oracle.sh",
    "/async_rbench/run-tests.sh",
    "/async_rbench/upstream_solutions",
    "/async_rbench-private",
)


@dataclass(frozen=True)
class PrivateVerificationResult:
    success: bool
    exit_code: int
    output: str
    verifier_bundle_sha256: str
    isolation: str = "filesystem-snapshot-clone"
    test_pass_fraction: float | None = None
    test_counts: dict[str, int] | None = None
    component_results: dict[str, dict[str, object]] | None = None
    test_point_pass_rate: float | None = None
    semantic_check_results: list[dict[str, object]] | None = None
    semantic_check_counts: dict[str, int] | None = None
    semantic_registry_version: str | None = None


def _load_semantic_registry(task_dir: Path) -> dict | None:
    path = task_dir / "tests" / "semantic_checks.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _safe_name(value: str, limit: int = 48) -> str:
    cleaned = re.sub(r"[^a-z0-9_.-]+", "-", value.lower()).strip("-.")
    return (cleaned or "episode")[:limit]


def tree_sha256(paths: list[Path]) -> str:
    """Digest file names and bytes without depending on filesystem metadata."""
    digest = hashlib.sha256()
    files: list[tuple[str, Path]] = []
    for root in paths:
        root = root.resolve()
        if root.is_file():
            files.append((root.name, root))
        elif root.is_dir():
            files.extend(
                (f"{root.name}/{path.relative_to(root).as_posix()}", path)
                for path in root.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
            )
        else:
            raise FileNotFoundError(root)
    for relative, path in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verifier_bundle_sha256(task_dir: Path) -> str:
    """Digest the exact private tests and runner used for one case."""
    return tree_sha256([task_dir / "tests", task_dir / "run-tests.sh"])


def audit_participant_container(
    container: str, *, allow_participant_tests_path: bool = False,
) -> None:
    """Fail if private evaluation material leaked into a participant image.

    ``/tests`` is checked during the clean-container preflight. After the agent
    has run, that generic path may legitimately contain tests written by the
    participant itself, so the final audit permits only that path while still
    rejecting every benchmark-private location.
    """
    forbidden_paths = tuple(
        path for path in FORBIDDEN_PARTICIPANT_PATHS
        if not (allow_participant_tests_path and path == "/tests")
    )
    command = "\n".join(
        f"if [ -e '{path}' ]; then printf '%s\\n' '{path}'; fi"
        for path in forbidden_paths
    )
    result = _docker("exec", container, "/bin/sh", "-c", command, check=False)
    leaked = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0:
        raise RuntimeError(f"participant contamination audit failed: {result.stdout[-4000:]}")
    if leaked:
        raise RuntimeError("participant image exposes private evaluation paths: " + ", ".join(leaked))


def _copy_private_bundle(container: str, task_dir: Path) -> None:
    tests = task_dir / "tests"
    runner = task_dir / "run-tests.sh"
    _docker("cp", str(tests.resolve()), f"{container}:/async_rbench_tests")
    _docker("exec", container, "mkdir", "-p", "/async_rbench-private")
    _docker("cp", str(runner.resolve()), f"{container}:/async_rbench-private/run-tests.sh")
    _docker("exec", container, "sed", "-i", r"s/\r$//", "/async_rbench-private/run-tests.sh")
    _docker("exec", container, "chmod", "0555", "/async_rbench-private/run-tests.sh")


def run_isolated_verifier(
    *, main_container: str, task_dir: Path, episode_id: str, timeout_sec: int = 1800
) -> PrivateVerificationResult:
    """Verify a frozen filesystem clone that the participant cannot access.

    Docker commit captures submitted filesystem state but no participant
    processes. The case verifier starts required services from that state.
    Hidden tests are copied only to the private clone.
    """
    # The runner already performed the strict audit (including /tests) before
    # exposing the clean participant container to the agent. At submission
    # time, keep auditing genuinely private paths but allow agent-authored
    # /tests; it is replaced only in the isolated verifier clone below.
    audit_participant_container(main_container, allow_participant_tests_path=True)
    suffix = uuid.uuid4().hex[:10]
    safe_episode = _safe_name(episode_id, 30)
    image = f"async_rbench-private-verifier-{safe_episode}-{suffix}:snapshot"
    container = _safe_name(f"dtb2v-{safe_episode}-{suffix}", 62)
    bundle_digest = verifier_bundle_sha256(task_dir)
    semantic_registry = _load_semantic_registry(task_dir)
    try:
        _docker("commit", main_container, image)
        _docker(
            "run", "-d", "--name", container, "--entrypoint", "/bin/sh",
            image, "-c", "sleep infinity",
        )
        _copy_private_bundle(container, task_dir)
        try:
            result = subprocess.run(
                ["docker", "exec", container, "/bin/bash", "/async_rbench-private/run-tests.sh"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_sec,
            )
            output = (result.stdout or b"").decode("utf-8", errors="replace")
            pytest_summary = parse_pytest_summary(output)
            component_results = parse_component_summaries(output)
            semantic = parse_semantic_check_results(output, semantic_registry)
            return PrivateVerificationResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                output=output,
                verifier_bundle_sha256=bundle_digest,
                test_pass_fraction=pytest_summary["test_pass_fraction"],
                test_counts={
                    key: int(pytest_summary[key])
                    for key in (
                        "passed", "failed", "errors", "counted", "skipped",
                        "deselected", "xfailed", "xpassed", "warnings",
                        "summary_lines",
                    )
                },
                component_results=component_results,
                test_point_pass_rate=(semantic or {}).get("test_point_pass_rate"),
                semantic_check_results=(semantic or {}).get("results"),
                semantic_check_counts=(
                    {"passed": int(semantic["passed"]), "total": int(semantic["total"])}
                    if semantic else None
                ),
                semantic_registry_version=(semantic or {}).get("registry_version"),
            )
        except subprocess.TimeoutExpired as exc:
            raw_output = exc.stdout or b""
            output = (
                raw_output.decode("utf-8", errors="replace")
                if isinstance(raw_output, bytes) else str(raw_output)
            )
            output += "\nprivate verifier timed out"
            pytest_summary = parse_pytest_summary(output)
            component_results = parse_component_summaries(output)
            semantic = parse_semantic_check_results(output, semantic_registry)
            return PrivateVerificationResult(
                False, 124, output, bundle_digest,
                test_pass_fraction=pytest_summary["test_pass_fraction"],
                test_counts={
                    key: int(pytest_summary[key])
                    for key in (
                        "passed", "failed", "errors", "counted", "skipped",
                        "deselected", "xfailed", "xpassed", "warnings",
                        "summary_lines",
                    )
                },
                component_results=component_results,
                test_point_pass_rate=(semantic or {}).get("test_point_pass_rate"),
                semantic_check_results=(semantic or {}).get("results"),
                semantic_check_counts=(
                    {"passed": int(semantic["passed"]), "total": int(semantic["total"])}
                    if semantic else None
                ),
                semantic_registry_version=(semantic or {}).get("registry_version"),
            )
    finally:
        _docker("rm", "-f", container, check=False)
        _docker("image", "rm", "-f", image, check=False)


def inject_oracle(container: str, task_dir: Path) -> None:
    """Install oracle material only in a benchmark-maintenance container."""
    _docker("exec", container, "mkdir", "-p", "/async_rbench")
    _docker("cp", str((task_dir / "oracle.sh").resolve()), f"{container}:/async_rbench/oracle.sh")
    solutions = task_dir / "upstream_solutions"
    if solutions.exists():
        _docker("cp", str(solutions.resolve()), f"{container}:/async_rbench/upstream_solutions")
    _docker("exec", container, "chmod", "0555", "/async_rbench/oracle.sh")
    _docker("exec", container, "sed", "-i", r"s/\r$//", "/async_rbench/oracle.sh")
    if solutions.exists():
        _docker(
            "exec", container, "/bin/sh", "-c",
            "for f in /async_rbench/upstream_solutions/*.sh; do sed -i 's/\\r$//' \"$f\"; done",
        )
        _docker("exec", container, "/bin/sh", "-c", "chmod 0555 /async_rbench/upstream_solutions/*.sh")


def remove_oracle(container: str) -> None:
    _docker(
        "exec", container, "rm", "-rf",
        "/async_rbench/oracle.sh", "/async_rbench/upstream_solutions",
        check=False,
    )
