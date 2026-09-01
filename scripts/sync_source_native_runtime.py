"""Atomically sync source-native manifest/report runtime metadata.

This command consumes existing local artifacts only.  It never regenerates
cases, contacts upstream sources, or turns infrastructure smoke into a model
episode claim.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.native_runtime_registry import (  # noqa: E402
    MARBLE_NATIVE_INITIALIZATION_PROFILE,
    NATIVE_ENVIRONMENT_INITIALIZATION_STATUS,
    NATIVE_RUNTIME_READY_STATUS,
    OSWORLD_NATIVE_PROFILE,
    READY_STATUS,
    read_registry,
    merge_registry_entries,
    replace_files_atomically,
    serialize_registry,
    serialize_runtime_metadata,
    synchronize_runtime_metadata,
)
from async_rbench.osworld_runtime import (  # noqa: E402
    OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
    osworld_provider_lock_path,
)
from async_rbench.unified_case_v3 import read_json, read_jsonl  # noqa: E402


TARGET_NATIVE_BENCHMARKS = frozenset({"OSWorld", "MultiAgentBench"})
SHA1_PATTERN = re.compile(r"[0-9a-f]{40}")
EXPECTED_OSWORLD_NATIVE_CASE_COUNT = 91


class SourceNativeSyncLockUnavailable(RuntimeError):
    """Raised when another process is synchronizing the same repository."""


class OSWorldBatchLockUnavailable(RuntimeError):
    """Raised when the canonical OSWorld batch is still running."""


def source_native_sync_lock_path(repository_root: Path) -> Path:
    """Return a host-local lock path keyed by the canonical repository root."""

    identity = os.path.normcase(str(repository_root.resolve())).encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / f"dtbench-source-native-sync-{suffix}.lock"


@contextmanager
def _exclusive_file_lock(path: Path, *, busy_error: RuntimeError):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    try:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise busy_error from exc
        acquired = True
        yield path
    finally:
        if acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


@contextmanager
def exclusive_source_native_sync_lock(repository_root: Path):
    """Serialize read/validate/replace across sync processes on this host."""

    resolved_root = repository_root.resolve()
    with _exclusive_file_lock(
        source_native_sync_lock_path(resolved_root),
        busy_error=SourceNativeSyncLockUnavailable(
            f"source-native sync is already running for {resolved_root}"
        ),
    ) as path:
        yield path


@contextmanager
def exclusive_osworld_batch_snapshot_lock(repository_root: Path):
    """Prevent OSWorld cases/report from changing while the sync commits them."""

    batch_root = (
        repository_root.resolve() / "artifacts/native-runtime-v4/osworld-native"
    )
    with _exclusive_file_lock(
        batch_root / ".osworld-native-batch.lock",
        busy_error=OSWorldBatchLockUnavailable(
            f"canonical OSWorld batch is still running: {batch_root}"
        ),
    ) as path:
        yield path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _official_marble_record_sha256(value: Any) -> str:
    """Match the producer's source-record digest, including JSON spacing."""

    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _resolve_contained(base: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is missing")
    candidate = Path(value)
    target = (candidate if candidate.is_absolute() else base / candidate).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes repository root") from exc
    return target


def _require_file(path: Path, *, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")


def _require_recorded_file_hash(
    candidate: Mapping[str, Any],
    *,
    path_field: str,
    hash_field: str,
    expected_path: Path,
    repository_root: Path,
    label: str,
) -> None:
    recorded_path = _resolve_contained(
        repository_root, candidate.get(path_field), label=f"{label} path"
    )
    if recorded_path != expected_path.resolve():
        raise ValueError(f"{label} path does not match the canonical repository path")
    _require_file(expected_path, label=label)
    if candidate.get(hash_field) != _sha256_file(expected_path):
        raise ValueError(f"{label} hash does not match the current repository file")


@lru_cache(maxsize=None)
def _require_pinned_git_tree(
    repository: str,
    revision: str,
    subtree: str,
    *,
    label: str,
) -> None:
    """Bind a tracked upstream implementation subtree to its pinned commit."""

    repo = Path(repository).resolve()
    if not SHA1_PATTERN.fullmatch(revision):
        raise ValueError(f"{label} pinned revision is invalid")
    try:
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        tree = subprocess.run(
            ["git", "-C", str(repo), "diff", "--quiet", revision, "--", subtree],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"{label} Git binding could not be verified") from exc
    if head.returncode != 0 or head.stdout.strip().lower() != revision:
        raise ValueError(f"{label} checkout does not match the pinned revision")
    if tree.returncode == 1:
        raise ValueError(
            f"{label} implementation tree differs from the pinned revision"
        )
    if tree.returncode != 0:
        raise ValueError(f"{label} Git implementation tree could not be verified")


def _native_candidates(entry: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    candidates: list[tuple[str, Mapping[str, Any]]] = []
    if entry.get("status") in {
        NATIVE_RUNTIME_READY_STATUS,
        NATIVE_ENVIRONMENT_INITIALIZATION_STATUS,
    }:
        candidates.append(("root", entry))
    for field in ("native_environment", "native_environment_initialization"):
        if field not in entry:
            continue
        nested = entry[field]
        if not isinstance(nested, Mapping):
            raise ValueError(f"runtime registry {field} must be an object")
        candidates.append((field, nested))
    return candidates


def _load_native_case(
    manifest_row: Mapping[str, Any], *, source_root: Path
) -> tuple[Path, dict[str, Any]]:
    cases_root = (source_root / "cases").resolve()
    case_dir = _resolve_contained(
        source_root, manifest_row.get("native_path"), label="manifest native_path"
    )
    try:
        case_dir.relative_to(cases_root)
    except ValueError as exc:
        raise ValueError("manifest native_path is outside source-native cases") from exc
    if case_dir.name != str(manifest_row.get("case_id") or ""):
        raise ValueError("manifest native_path directory does not match case_id")
    spec_path = case_dir / "native_case.json"
    _require_file(spec_path, label="native case spec")
    spec = read_json(spec_path)
    if not isinstance(spec, dict):
        raise ValueError("native case spec is not an object")
    for field in ("case_id", "benchmark"):
        if spec.get(field) != manifest_row.get(field):
            raise ValueError(f"native case spec {field} does not match manifest")
    return case_dir, spec


def _validate_osworld_source_binding(
    candidate: Mapping[str, Any],
    manifest_row: Mapping[str, Any],
    *,
    source_root: Path,
    repository_root: Path,
) -> None:
    if (
        candidate.get("status") != NATIVE_RUNTIME_READY_STATUS
        or candidate.get("qualification_profile") != OSWORLD_NATIVE_PROFILE
    ):
        raise ValueError("OSWorld native evidence uses an unsupported status/profile")
    _case_dir, spec = _load_native_case(manifest_row, source_root=source_root)
    binding = spec.get("source_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("OSWorld source binding is missing")
    task_id = str(binding.get("task_id") or "")
    domain = str(binding.get("domain") or "")
    expected_source_task_id = f"osworld:{domain}:{task_id}"
    if (
        not task_id
        or not domain
        or expected_source_task_id != manifest_row.get("source_task_id")
    ):
        raise ValueError("OSWorld source task identity does not match the case spec")

    upstream_root = (repository_root / "upstream/osworld").resolve()
    upstream_revision = str(binding.get("upstream_revision") or "").lower()
    _require_pinned_git_tree(
        str(upstream_root),
        upstream_revision,
        "desktop_env",
        label="OSWorld upstream",
    )

    config_path = _resolve_contained(
        repository_root,
        binding.get("config_path"),
        label="OSWorld official config path",
    )
    official_examples = (
        repository_root / "upstream/osworld/evaluation_examples/examples"
    ).resolve()
    try:
        config_path.relative_to(official_examples)
    except ValueError as exc:
        raise ValueError("OSWorld official config is outside pinned examples") from exc
    _require_file(config_path, label="OSWorld official config")
    config_sha256 = _sha256_file(config_path)
    if binding.get("config_sha256") != config_sha256:
        raise ValueError("OSWorld case spec config hash does not match upstream")
    task = read_json(config_path)
    if not isinstance(task, dict) or str(task.get("id") or "") != task_id:
        raise ValueError("OSWorld official config task identity is invalid")
    evaluator = task.get("evaluator")
    evaluator_sha256 = _canonical_sha256(evaluator)
    if _canonical_sha256(spec.get("native_evaluator")) != evaluator_sha256:
        raise ValueError("OSWorld native evaluator no longer matches upstream")
    if candidate.get("official_task_config_sha256") != config_sha256:
        raise ValueError("OSWorld evidence config hash is not case-bound")
    if candidate.get("official_evaluator_source_sha256") != evaluator_sha256:
        raise ValueError("OSWorld evidence evaluator hash is not case-bound")
    evaluator_probe = candidate.get("evaluator_probe")
    if not isinstance(evaluator_probe, Mapping):
        raise ValueError("OSWorld evaluator probe is missing")
    if evaluator_probe.get("task_evaluator_sha256") != evaluator_sha256:
        raise ValueError("OSWorld evaluator probe hash is not case-bound")
    if evaluator_probe.get("evaluator_func") != (
        evaluator.get("func") if isinstance(evaluator, Mapping) else None
    ):
        raise ValueError("OSWorld evaluator probe function is not case-bound")

    phase_hashes = {
        "first_reset_task_setup": _canonical_sha256(task.get("config", [])),
        "official_evaluator_postconfig": _canonical_sha256(
            evaluator.get("postconfig", []) if isinstance(evaluator, Mapping) else []
        ),
        "second_reset_task_setup": _canonical_sha256(task.get("config", [])),
    }
    setup_probe = candidate.get("setup_probe")
    calls = setup_probe.get("calls") if isinstance(setup_probe, Mapping) else None
    if not isinstance(calls, list):
        raise ValueError("OSWorld setup probe calls are missing")
    for phase, expected_hash in phase_hashes.items():
        phase_calls = [
            call
            for call in calls
            if isinstance(call, Mapping) and call.get("phase") == phase
        ]
        if not phase_calls or any(
            call.get("config_sha256") != expected_hash for call in phase_calls
        ):
            raise ValueError(f"OSWorld setup probe is not case-bound for {phase}")

    details = (candidate.get("provider_preflight") or {}).get("details")
    if not isinstance(details, Mapping):
        raise ValueError("OSWorld provider preflight details are missing")
    for relative_path, hash_field, label in (
        ("desktop_env/providers/__init__.py", "factory_sha256", "provider factory"),
        (
            "desktop_env/providers/docker/provider.py",
            "provider_source_sha256",
            "Docker provider",
        ),
        (
            "desktop_env/providers/docker/manager.py",
            "manager_source_sha256",
            "Docker manager",
        ),
    ):
        source_path = upstream_root / relative_path
        _require_file(source_path, label=f"OSWorld {label} source")
        if details.get(hash_field) != _sha256_file(source_path):
            raise ValueError(f"OSWorld {label} source hash is not current")
    canonical_asset = (
        repository_root
        / "artifacts/native-runtime-v4/osworld-assets/asset_attestation.json"
    ).resolve()
    canonical_bootstrap = (
        repository_root / ".venv-osworld-native/osworld-native-bootstrap-report.json"
    ).resolve()
    canonical_lock = (
        repository_root / "configs/osworld-native-requirements.lock"
    ).resolve()
    _require_recorded_file_hash(
        details,
        path_field="asset_attestation_path",
        hash_field="asset_attestation_sha256",
        expected_path=canonical_asset,
        repository_root=repository_root,
        label="OSWorld asset attestation",
    )
    _require_recorded_file_hash(
        details,
        path_field="python_bootstrap_report_path",
        hash_field="python_bootstrap_report_sha256",
        expected_path=canonical_bootstrap,
        repository_root=repository_root,
        label="OSWorld Python bootstrap report",
    )
    _require_recorded_file_hash(
        details,
        path_field="python_environment_lock_path",
        hash_field="python_environment_lock_sha256",
        expected_path=canonical_lock,
        repository_root=repository_root,
        label="OSWorld Python environment lock",
    )
    canonical_vm = (
        repository_root / "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
    ).resolve()
    _require_file(canonical_vm, label="OSWorld VM disk")
    recorded_vm = _resolve_contained(
        repository_root, details.get("vm_disk_path"), label="OSWorld VM disk path"
    )
    if recorded_vm != canonical_vm:
        raise ValueError("OSWorld VM disk path is not canonical")


def _validate_marble_source_binding(
    candidate: Mapping[str, Any],
    manifest_row: Mapping[str, Any],
    *,
    source_root: Path,
    repository_root: Path,
) -> None:
    if (
        candidate.get("status") != NATIVE_ENVIRONMENT_INITIALIZATION_STATUS
        or candidate.get("qualification_profile")
        != MARBLE_NATIVE_INITIALIZATION_PROFILE
    ):
        raise ValueError("MARBLE native evidence uses an unsupported status/profile")
    case_dir, spec = _load_native_case(manifest_row, source_root=source_root)
    binding = spec.get("source_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("MARBLE source binding is missing")
    source_task_id = str(manifest_row.get("source_task_id") or "")
    scenario = source_task_id.split(":", 1)[0]
    if (
        binding.get("task_id") != source_task_id
        or binding.get("scenario") != scenario
        or candidate.get("scenario") != scenario
    ):
        raise ValueError("MARBLE scenario/source identity is not case-bound")

    config_path = case_dir / "native_config.yaml"
    spec_path = case_dir / "native_case.json"
    official_task_path = case_dir / "official_task.json"
    for path, label in (
        (config_path, "MARBLE native config"),
        (official_task_path, "MARBLE official task"),
    ):
        _require_file(path, label=label)
    source_evidence = candidate.get("source_evidence")
    if not isinstance(source_evidence, Mapping):
        raise ValueError("MARBLE native source evidence is missing")
    expected_hashes = {
        "native_config_sha256": _sha256_file(config_path),
        "native_case_sha256": _sha256_file(spec_path),
        "official_task_sha256": _sha256_file(official_task_path),
    }
    for field, expected in expected_hashes.items():
        if source_evidence.get(field) != expected:
            raise ValueError(f"MARBLE evidence {field} is not case-bound")

    source_path = _resolve_contained(
        repository_root,
        binding.get("jsonl_path"),
        label="MARBLE source JSONL path",
    )
    marble_sources = (repository_root / "upstream/marble/multiagentbench").resolve()
    try:
        source_path.relative_to(marble_sources)
    except ValueError as exc:
        raise ValueError("MARBLE source JSONL is outside pinned sources") from exc
    _require_file(source_path, label="MARBLE source JSONL")
    line_number = binding.get("line_number")
    if (
        not isinstance(line_number, int)
        or isinstance(line_number, bool)
        or line_number < 1
    ):
        raise ValueError("MARBLE source line number is invalid")
    lines = source_path.read_text(encoding="utf-8").splitlines()
    if line_number > len(lines):
        raise ValueError("MARBLE source line is out of range")
    record = json.loads(lines[line_number - 1])
    record_sha256 = _official_marble_record_sha256(record)
    if binding.get("record_sha256") != record_sha256:
        raise ValueError("MARBLE case spec source hash does not match upstream")
    expected_relative = str(source_path.relative_to(repository_root)).replace("\\", "/")
    if (
        source_evidence.get("jsonl_path") != expected_relative
        or source_evidence.get("line_number") != line_number
        or source_evidence.get("record_sha256") != record_sha256
    ):
        raise ValueError("MARBLE evidence source record is not case-bound")

    runtime_binding = candidate.get("runtime_binding")
    if not isinstance(runtime_binding, Mapping):
        raise ValueError("MARBLE runtime binding is missing")
    canonical_lock = (
        repository_root / "configs/marble-native-requirements.lock"
    ).resolve()
    canonical_lock_artifact = (
        repository_root / "artifacts/native-runtime-v4/marble_native_dependencies.lock"
    ).resolve()
    canonical_bootstrap = (
        repository_root / "artifacts/native-runtime-v4/marble_bootstrap_report.json"
    ).resolve()
    _require_recorded_file_hash(
        runtime_binding,
        path_field="dependency_lock_path",
        hash_field="dependency_lock_sha256",
        expected_path=canonical_lock,
        repository_root=repository_root,
        label="MARBLE dependency lock",
    )
    _require_recorded_file_hash(
        runtime_binding,
        path_field="dependency_lock_artifact_path",
        hash_field="dependency_lock_artifact_sha256",
        expected_path=canonical_lock_artifact,
        repository_root=repository_root,
        label="MARBLE dependency lock artifact",
    )
    if canonical_lock.read_bytes() != canonical_lock_artifact.read_bytes():
        raise ValueError("MARBLE dependency lock artifact differs from canonical input")
    _require_recorded_file_hash(
        runtime_binding,
        path_field="bootstrap_report_path",
        hash_field="bootstrap_report_sha256",
        expected_path=canonical_bootstrap,
        repository_root=repository_root,
        label="MARBLE bootstrap report",
    )


def validate_source_bound_native_evidence(
    entry: Mapping[str, Any],
    manifest_row: Mapping[str, Any],
    *,
    source_root: Path,
    repository_root: Path,
) -> None:
    """Reject native evidence that is not bound to the current canonical case."""

    benchmark = str(manifest_row.get("benchmark") or "")
    if benchmark not in TARGET_NATIVE_BENCHMARKS:
        return
    for field in ("case_id", "benchmark", "source_task_id"):
        if str(entry.get(field) or "") != str(manifest_row.get(field) or ""):
            raise ValueError(
                f"runtime registry source binding identity mismatch: {field}"
            )
    if entry.get("status") == READY_STATUS:
        raise ValueError(
            f"legacy gold/checkpoint evidence is not accepted for {benchmark}"
        )
    for location, candidate in _native_candidates(entry):
        for field in ("case_id", "benchmark", "source_task_id"):
            if str(candidate.get(field) or "") != str(manifest_row.get(field) or ""):
                raise ValueError(
                    f"{benchmark} {location} native evidence identity mismatch: {field}"
                )
        if benchmark == "OSWorld":
            _validate_osworld_source_binding(
                candidate,
                manifest_row,
                source_root=source_root,
                repository_root=repository_root,
            )
        else:
            _validate_marble_source_binding(
                candidate,
                manifest_row,
                source_root=source_root,
                repository_root=repository_root,
            )


def validate_registry_source_bindings(
    registry: Mapping[str, Mapping[str, Any]],
    manifest: Iterable[Mapping[str, Any]],
    *,
    source_root: Path,
    repository_root: Path,
) -> None:
    manifest_by_id = {str(row.get("case_id") or ""): row for row in manifest}
    for case_id, entry in registry.items():
        row = manifest_by_id.get(case_id)
        if row is None:
            continue
        validate_source_bound_native_evidence(
            entry,
            row,
            source_root=source_root,
            repository_root=repository_root,
        )


def require_complete_benchmark_tier(
    manifest: Iterable[Mapping[str, Any]],
    benchmark: str,
    benchmark_counts: Mapping[str, Any],
    *,
    tier_label: str,
) -> None:
    """Fail unless every manifest row in a benchmark passed one evidence tier."""

    expected = sum(str(row.get("benchmark") or "") == benchmark for row in manifest)
    ready = benchmark_counts.get(benchmark, 0)
    if expected == 0:
        raise ValueError(f"required benchmark is absent from manifest: {benchmark}")
    if not isinstance(ready, int) or isinstance(ready, bool) or ready != expected:
        raise ValueError(
            f"required benchmark is not fully {tier_label}: "
            f"{benchmark} ({ready}/{expected})"
        )


def _validated_osworld_live_phase(
    value: Any,
    *,
    label: str,
    require_identity_stable_claim: bool,
) -> dict[str, Any]:
    """Recompute the batch's Docker/VM live-gate invariants from its report."""

    if not isinstance(value, Mapping) or value.get("validated") is not True:
        raise ValueError(f"OSWorld batch {label} was not validated")
    if value.get("daemon_identity_matches") is not True:
        raise ValueError(f"OSWorld batch {label} CLI/SDK daemon mismatch")
    if (
        require_identity_stable_claim
        and value.get("preflight_postflight_identity_stable") is not True
    ):
        raise ValueError("OSWorld batch provider identity was not stable")

    provider = value.get("provider")
    kvm_probe = value.get("kvm_probe")
    cli = value.get("docker_cli_daemon")
    sdk = value.get("docker_sdk_provider")
    containers = value.get("container_probe")
    provider_lock = value.get("provider_vm_lock")
    if not all(
        isinstance(item, Mapping)
        for item in (provider, kvm_probe, cli, sdk, containers, provider_lock)
    ):
        raise ValueError(f"OSWorld batch {label} live evidence is malformed")
    if not all(
        (
            provider_lock.get("acquired") is True,
            isinstance(provider_lock.get("path"), str),
            bool(provider_lock.get("path")),
            provider_lock.get("error") in (None, ""),
        )
    ):
        raise ValueError(f"OSWorld batch {label} provider lock was not acquired")

    provider_details = provider.get("details")
    if not isinstance(provider_details, Mapping) or not all(
        (
            provider.get("provider") == "docker",
            provider.get("configuration_resolved") is True,
            provider.get("launch_ready") is True,
            provider.get("blockers") == [],
            provider_details.get("daemon_reachable") is True,
            provider_details.get("docker_image_present") is True,
            provider_details.get("docker_digest_image_present") is True,
            provider_details.get("docker_latest_image_present") is True,
            provider_details.get("docker_image_identity")
            == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
            provider_details.get("docker_digest_image_identity")
            == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
            provider_details.get("docker_latest_image_identity")
            == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
            provider_details.get("vm_disk_present") is True,
            provider_details.get("asset_attestation_verified") is True,
            provider_details.get("python_bootstrap_verified") is True,
        )
    ):
        raise ValueError(f"OSWorld batch {label} provider evidence is invalid")

    kvm_available = kvm_probe.get("device_available")
    kvm_exit = kvm_probe.get("exit_code")
    if not (
        isinstance(kvm_available, bool)
        and (
            (
                isinstance(kvm_exit, int)
                and not isinstance(kvm_exit, bool)
                and ((kvm_exit == 0) is kvm_available)
            )
            or (kvm_exit is None and kvm_available is False)
        )
    ):
        raise ValueError(f"OSWorld batch {label} KVM probe is invalid")

    identity_keys = {
        "id",
        "name",
        "server_version",
        "docker_root_dir",
        "os_type",
        "architecture",
    }
    cli_identity = cli.get("daemon_identity")
    sdk_identity = sdk.get("daemon_identity")
    if not all(
        (
            cli.get("probe_succeeded") is True,
            sdk.get("probe_succeeded") is True,
            isinstance(cli.get("context"), str),
            bool(cli.get("context")),
            isinstance(cli_identity, Mapping),
            isinstance(sdk_identity, Mapping),
            (
                all(cli_identity.get(key) for key in identity_keys)
                if isinstance(cli_identity, Mapping)
                else False
            ),
            (
                all(sdk_identity.get(key) for key in identity_keys)
                if isinstance(sdk_identity, Mapping)
                else False
            ),
            (
                all(
                    cli_identity.get(key) == sdk_identity.get(key)
                    for key in identity_keys
                )
                if isinstance(cli_identity, Mapping)
                and isinstance(sdk_identity, Mapping)
                else False
            ),
        )
    ):
        raise ValueError(f"OSWorld batch {label} daemon identity is invalid")

    expected_sdk_checks = {
        "ping_succeeded",
        "daemon_identity_complete",
        "official_images_match",
        "minimal_container_created",
        "exact_vm_file_bind_read_only",
        "kvm_or_tcg_probe_succeeded",
        "minimal_container_cleanup_succeeded",
    }
    sdk_checks = sdk.get("checks")
    minimal = sdk.get("minimal_container_probe")
    image_identities = sdk.get("image_identities")
    if not all(
        (
            sdk.get("ping_succeeded") is True,
            isinstance(sdk.get("client_base_url"), str),
            bool(sdk.get("client_base_url")),
            isinstance(sdk_checks, Mapping),
            (
                set(sdk_checks) == expected_sdk_checks
                if isinstance(sdk_checks, Mapping)
                else False
            ),
            (
                all(sdk_checks.get(key) is True for key in expected_sdk_checks)
                if isinstance(sdk_checks, Mapping)
                else False
            ),
            isinstance(image_identities, Mapping),
            (
                set(image_identities) == {"untagged", "digest", "latest"}
                if isinstance(image_identities, Mapping)
                else False
            ),
            (
                all(
                    image_identities.get(key) == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID
                    for key in ("untagged", "digest", "latest")
                )
                if isinstance(image_identities, Mapping)
                else False
            ),
            isinstance(minimal, Mapping),
            minimal.get("created") is True if isinstance(minimal, Mapping) else False,
            (
                minimal.get("mount_read_only") is True
                if isinstance(minimal, Mapping)
                else False
            ),
            minimal.get("exit_code") == 0 if isinstance(minimal, Mapping) else False,
            (
                minimal.get("cleanup_attempted") is True
                if isinstance(minimal, Mapping)
                else False
            ),
            (
                minimal.get("cleanup_succeeded") is True
                if isinstance(minimal, Mapping)
                else False
            ),
            (
                minimal.get("residual_container_present") is False
                if isinstance(minimal, Mapping)
                else False
            ),
        )
    ):
        raise ValueError(f"OSWorld batch {label} SDK provider probe is invalid")

    if not all(
        (
            containers.get("probe_succeeded") is True,
            containers.get("official_container_ids") == [],
            containers.get("provider_container_ids") == [],
        )
    ):
        raise ValueError(f"OSWorld batch {label} left provider containers")
    return {
        "cli_identity": dict(cli_identity),
        "sdk_identity": dict(sdk_identity),
        "context": cli.get("context"),
        "client_base_url": sdk.get("client_base_url"),
        "image_identities": dict(image_identities),
        "provider_lock_path": provider_lock.get("path"),
    }


def validate_osworld_full_batch_report(
    manifest: Iterable[Mapping[str, Any]],
    registry: Mapping[str, Mapping[str, Any]],
    *,
    repository_root: Path,
) -> None:
    """Authorize OSWorld promotion only from the canonical validated full batch."""

    osworld_rows = [
        row for row in manifest if str(row.get("benchmark") or "") == "OSWorld"
    ]
    expected_ids = {str(row.get("case_id") or "") for row in osworld_rows}
    if (
        len(osworld_rows) != EXPECTED_OSWORLD_NATIVE_CASE_COUNT
        or len(expected_ids) != EXPECTED_OSWORLD_NATIVE_CASE_COUNT
        or "" in expected_ids
    ):
        raise ValueError(
            "OSWorld canonical manifest is not the exact 91-case collection"
        )

    batch_root = (
        repository_root / "artifacts/native-runtime-v4/osworld-native"
    ).resolve()
    report_path = batch_root / "batch_report.json"
    _require_file(report_path, label="OSWorld canonical full batch report")
    report = read_json(report_path)
    if not isinstance(report, Mapping):
        raise ValueError("OSWorld canonical full batch report is malformed")
    fixed = {
        "schema_version": "osworld-native-batch-v1",
        "status": NATIVE_RUNTIME_READY_STATUS,
        "full_collection_requested": True,
        "expected_full_collection_count": EXPECTED_OSWORLD_NATIVE_CASE_COUNT,
        "discovered_case_count": EXPECTED_OSWORLD_NATIVE_CASE_COUNT,
        "unique_case_count": EXPECTED_OSWORLD_NATIVE_CASE_COUNT,
        "selected_case_count": EXPECTED_OSWORLD_NATIVE_CASE_COUNT,
        "all_91_selected": True,
        "all_91_explicitly_selected": True,
        "full_collection_validated": True,
        "native_environment_validated_count": EXPECTED_OSWORLD_NATIVE_CASE_COUNT,
        "failed_count": 0,
        "registry_merged": False,
        "atomic_sync_required": True,
        "status_required": NATIVE_RUNTIME_READY_STATUS,
    }
    if any(report.get(key) != value for key, value in fixed.items()):
        raise ValueError("OSWorld canonical full batch report is not promotable")
    sync_command = report.get("sync_command")
    if not isinstance(sync_command, str) or not all(
        token in sync_command
        for token in (
            "sync_source_native_runtime.py",
            "--require-ready-benchmark OSWorld",
        )
    ):
        raise ValueError(
            "OSWorld batch report does not require the canonical ready gate"
        )

    preflight = _validated_osworld_live_phase(
        report.get("live_provider_preflight"),
        label="preflight",
        require_identity_stable_claim=False,
    )
    postflight = _validated_osworld_live_phase(
        report.get("live_provider_postflight"),
        label="postflight",
        require_identity_stable_claim=True,
    )
    if any(
        preflight[field] != postflight[field]
        for field in (
            "cli_identity",
            "sdk_identity",
            "context",
            "client_base_url",
            "image_identities",
            "provider_lock_path",
        )
    ):
        raise ValueError("OSWorld Docker provider changed during the full batch")
    canonical_vm = (
        repository_root / "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
    ).resolve()
    if Path(
        str(preflight["provider_lock_path"])
    ).resolve() != osworld_provider_lock_path(canonical_vm):
        raise ValueError("OSWorld batch did not use the canonical provider lock")

    cases_root = (batch_root / "cases").resolve()
    _require_file(report_path, label="OSWorld canonical full batch report")
    actual_case_paths = {
        path.stem: path.resolve()
        for path in cases_root.glob("*.json")
        if path.is_file()
    }
    if set(actual_case_paths) != expected_ids:
        raise ValueError(
            "OSWorld canonical batch evidence is not the exact 91-case set"
        )
    results = report.get("results")
    if not isinstance(results, list) or len(results) != len(expected_ids):
        raise ValueError("OSWorld canonical batch result count is invalid")
    results_by_id: dict[str, Mapping[str, Any]] = {}
    for result in results:
        if not isinstance(result, Mapping):
            raise ValueError("OSWorld canonical batch result is malformed")
        case_id = str(result.get("case_id") or "")
        if case_id in results_by_id:
            raise ValueError(f"OSWorld batch result is duplicated: {case_id}")
        results_by_id[case_id] = result
    if set(results_by_id) != expected_ids:
        raise ValueError("OSWorld canonical batch results do not match the manifest")

    for case_id in sorted(expected_ids):
        result = results_by_id[case_id]
        evidence_path = actual_case_paths[case_id]
        recorded_path = _resolve_contained(
            repository_root,
            result.get("evidence_path"),
            label=f"OSWorld batch evidence path for {case_id}",
        )
        if recorded_path != evidence_path:
            raise ValueError(f"OSWorld batch evidence path is not canonical: {case_id}")
        evidence_file_sha256 = _sha256_file(evidence_path)
        if not all(
            (
                result.get("return_code") == 0,
                result.get("status") == NATIVE_RUNTIME_READY_STATUS,
                result.get("qualified") is True,
                result.get("reason") is None,
                result.get("evidence_file_sha256") == evidence_file_sha256,
            )
        ):
            raise ValueError(f"OSWorld batch result is not promotable: {case_id}")
        evidence = read_json(evidence_path)
        if not isinstance(evidence, Mapping) or not all(
            (
                evidence.get("case_id") == case_id,
                evidence.get("benchmark") == "OSWorld",
                evidence.get("status") == NATIVE_RUNTIME_READY_STATUS,
                isinstance(evidence.get("evidence_sha256"), str),
            )
        ):
            raise ValueError(f"OSWorld batch evidence is malformed: {case_id}")
        registry_entry = registry.get(case_id)
        if not isinstance(registry_entry, Mapping) or not any(
            candidate.get("evidence_sha256") == evidence.get("evidence_sha256")
            and candidate.get("status") == NATIVE_RUNTIME_READY_STATUS
            for _location, candidate in _native_candidates(registry_entry)
        ):
            raise ValueError(
                f"OSWorld batch evidence does not match the merged registry: {case_id}"
            )


def read_evidence_path(path: Path) -> dict[str, dict]:
    if path.is_file() and path.suffix.lower() == ".jsonl":
        return read_registry(path)
    if path.is_file():
        candidates = [path]
    elif path.is_dir():
        evidence_dir = path / "cases" if (path / "cases").is_dir() else path
        candidates = sorted(evidence_dir.glob("*.json"))
    else:
        raise ValueError(f"runtime evidence path does not exist: {path}")
    entries: dict[str, dict] = {}
    for candidate in candidates:
        entry = read_json(candidate)
        case_id = str(entry.get("case_id") or "") if isinstance(entry, dict) else ""
        if not case_id:
            raise ValueError(f"runtime evidence has no case_id: {candidate}")
        if case_id in entries:
            raise ValueError(f"duplicate runtime evidence case_id: {case_id}")
        entries[case_id] = entry
    if not entries:
        raise ValueError(f"runtime evidence path contains no entries: {path}")
    return entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="artifacts/source-native-v4")
    parser.add_argument(
        "--runtime-registry",
        default="artifacts/native-runtime-v4/runtime_registry.jsonl",
    )
    parser.add_argument(
        "--repository-root",
        default=str(ROOT),
        help="Repository root used for canonical source and runtime-file binding",
    )
    parser.add_argument(
        "--merge-evidence",
        action="append",
        default=[],
        help="Merge a JSONL file, JSON file, or case-evidence directory before syncing",
    )
    parser.add_argument(
        "--check", action="store_true", help="Report drift without writing"
    )
    parser.add_argument(
        "--require-ready-benchmark",
        action="append",
        default=[],
        help="Fail before writing unless every manifest case in this benchmark is runtime-ready",
    )
    parser.add_argument(
        "--require-initialized-benchmark",
        action="append",
        default=[],
        help=(
            "Fail before writing unless every manifest case in this benchmark has "
            "validated native-environment initialization evidence"
        ),
    )
    parser.add_argument(
        "--require-smoke-ready-benchmark",
        action="append",
        default=[],
        help="Fail unless every case has environment-smoke evidence; does not imply runtime readiness",
    )
    return parser.parse_args()


def run_sync(args: argparse.Namespace) -> int:
    artifact_root = Path(args.root).resolve()
    repository_root = Path(args.repository_root).resolve()
    manifest_path = artifact_root / "native_manifest.jsonl"
    report_path = artifact_root / "production_report.json"
    registry_path = Path(args.runtime_registry).resolve()
    current_manifest_bytes = manifest_path.read_bytes()
    current_report_bytes = report_path.read_bytes()
    current_registry_bytes = (
        registry_path.read_bytes() if registry_path.is_file() else b""
    )
    current_manifest = read_jsonl(manifest_path)
    current_report = read_json(report_path)
    registry = read_registry(registry_path)
    manifest_ids = {str(row.get("case_id") or "") for row in current_manifest}
    incoming_ids: set[str] = set()
    for evidence_path_value in args.merge_evidence:
        evidence_path = Path(evidence_path_value).resolve()
        evidence = read_evidence_path(evidence_path)
        unknown = sorted(set(evidence) - manifest_ids)
        if unknown:
            raise ValueError(
                "runtime evidence case_id is absent from the source-native manifest: "
                + ", ".join(unknown[:5])
            )
        duplicates = sorted(incoming_ids.intersection(evidence))
        if duplicates:
            raise ValueError(
                "case_id appears in more than one --merge-evidence input: "
                + ", ".join(duplicates[:5])
            )
        incoming_ids.update(evidence)
        for case_id, entry in evidence.items():
            registry[case_id] = (
                merge_registry_entries(registry[case_id], entry)
                if case_id in registry
                else entry
            )
    validate_registry_source_bindings(
        registry,
        current_manifest,
        source_root=artifact_root,
        repository_root=repository_root,
    )
    manifest, report, summary = synchronize_runtime_metadata(
        current_manifest,
        current_report,
        registry,
        model_evidence_root=registry_path.parent,
    )

    osworld_ready_count = summary["runtime_ready_benchmark_counts"].get("OSWorld", 0)
    if osworld_ready_count:
        # OSWorld native evidence is promotable only as the canonical full batch.
        # The CLI flag is an additional assertion, not an opt-in security gate.
        require_complete_benchmark_tier(
            manifest,
            "OSWorld",
            summary["runtime_ready_benchmark_counts"],
            tier_label="runtime-ready",
        )
        validate_osworld_full_batch_report(
            manifest,
            registry,
            repository_root=repository_root,
        )

    for benchmark in args.require_ready_benchmark:
        require_complete_benchmark_tier(
            manifest,
            benchmark,
            summary["runtime_ready_benchmark_counts"],
            tier_label="runtime-ready",
        )
    for benchmark in args.require_initialized_benchmark:
        require_complete_benchmark_tier(
            manifest,
            benchmark,
            summary["native_environment_initialization_benchmark_counts"],
            tier_label="native-environment-initialized",
        )
    for benchmark in args.require_smoke_ready_benchmark:
        expected = sum(str(row["benchmark"]) == benchmark for row in manifest)
        ready = summary["environment_smoke_ready_benchmark_counts"].get(benchmark, 0)
        if expected == 0:
            raise ValueError(f"required benchmark is absent from manifest: {benchmark}")
        if ready != expected:
            raise ValueError(
                f"required benchmark lacks complete environment-smoke evidence: {benchmark} ({ready}/{expected})"
            )

    manifest_bytes, report_bytes = serialize_runtime_metadata(manifest, report)
    registry_bytes = serialize_registry(registry.values())
    registry_drift = current_registry_bytes != registry_bytes
    metadata_drift = (
        current_manifest_bytes != manifest_bytes or current_report_bytes != report_bytes
    )
    drift = registry_drift or metadata_drift
    summary["drift_detected"] = drift
    summary["write_performed"] = bool(drift and not args.check)
    summary["merged_evidence_count"] = len(incoming_ids)
    if drift and not args.check:
        if (
            manifest_path.read_bytes() != current_manifest_bytes
            or report_path.read_bytes() != current_report_bytes
        ):
            raise RuntimeError(
                "source-native metadata changed concurrently; rerun sync"
            )
        if (
            registry_path.read_bytes() if registry_path.is_file() else b""
        ) != current_registry_bytes:
            raise RuntimeError("runtime registry changed concurrently; rerun sync")
        _require_pinned_git_tree.cache_clear()
        validate_registry_source_bindings(
            registry,
            current_manifest,
            source_root=artifact_root,
            repository_root=repository_root,
        )
        if "OSWorld" in args.require_ready_benchmark:
            validate_osworld_full_batch_report(
                manifest,
                registry,
                repository_root=repository_root,
            )
        replacements = []
        if registry_drift:
            replacements.append((registry_path, registry_bytes))
        if metadata_drift:
            replacements.extend(
                ((manifest_path, manifest_bytes), (report_path, report_bytes))
            )
        replace_files_atomically(replacements)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if args.check and drift else 0


def main() -> int:
    args = parse_args()
    repository_root = Path(args.repository_root).resolve()
    with exclusive_source_native_sync_lock(repository_root):
        with exclusive_osworld_batch_snapshot_lock(repository_root):
            return run_sync(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(
            json.dumps(
                {"status": "sync_rejected", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(2)
