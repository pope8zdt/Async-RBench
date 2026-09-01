"""Run selected OSWorld native-v2 qualifications sequentially and resumably.

Nothing is selected implicitly: callers must repeat ``--case-id`` or pass the
explicit ``--all`` switch. This runner never writes canonical registry or
manifest metadata; the separate atomic sync command consumes its evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OSWORLD_VM_PATH = "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.native_runtime_registry import (  # noqa: E402
    NATIVE_RUNTIME_READY_STATUS,
    qualification,
)
from async_rbench.osworld_runtime import (  # noqa: E402
    OFFICIAL_OSWORLD_DOCKER_IMAGE,
    OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
    load_osworld_cases,
    osworld_provider_lock_path,
    probe_real_vm_provider,
    validate_osworld_python_bootstrap,
)
from scripts.run_osworld_native_case import (  # noqa: E402
    canonical_digest as canonical_case_digest,
    probe_docker_kvm_device,
    utf8_subprocess_environment,
)


EXPECTED_OSWORLD_CASE_COUNT = 91
OSWORLD_DOCKER_IMAGE = "happysixd/osworld-docker"


def docker_bind_source_matches_file(source: Any, vm_path: Path) -> bool:
    """Match one exact host file across Windows/Docker Desktop path dialects.

    Docker Desktop may return ``/run/desktop/mnt/host/f/...`` from an inspect
    even though docker-py submitted ``F:\\...``.  Compare complete normalized
    paths only; a parent-directory bind must never satisfy this check.
    """

    if not isinstance(source, str) or not source.strip():
        return False
    expected = str(vm_path.resolve()).replace("\\", "/").rstrip("/")
    actual = source.strip().replace("\\", "/").rstrip("/")
    candidates = {expected.casefold()}
    if len(expected) >= 3 and expected[1:3] == ":/":
        drive = expected[0].casefold()
        tail = expected[3:].lstrip("/")
        candidates.update({
            f"/run/desktop/mnt/host/{drive}/{tail}".casefold(),
            f"/host_mnt/{drive}/{tail}".casefold(),
        })
    return actual.casefold() in candidates


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.casefold())
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(20):
            try:
                os.replace(temporary_path, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.01)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_upstream_git_binding(upstream_root: Path) -> dict[str, Any]:
    """Bind runtime acceptance to the pinned, clean OSWorld checkout."""

    result: dict[str, Any] = {
        "probe_succeeded": False,
        "revision": "",
        "tracked_tree_clean": False,
    }
    try:
        revision = subprocess.run(
            ["git", "-C", str(upstream_root), "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=20,
        )
        status = subprocess.run(
            [
                "git", "-C", str(upstream_root), "status", "--porcelain",
                "--untracked-files=no",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = type(exc).__name__
        return result
    result.update({
        "revision": revision.stdout.strip() if revision.returncode == 0 else "",
        "tracked_tree_clean": status.returncode == 0 and not status.stdout.strip(),
    })
    result["probe_succeeded"] = bool(result["revision"]) and result["tracked_tree_clean"]
    if not result["probe_succeeded"]:
        result["detail"] = (
            revision.stderr or status.stderr or status.stdout or "upstream_binding_failed"
        ).strip()[-300:]
    return result


def qualify_entry_safely(
    entry: Any,
    *,
    source_task_id: str,
) -> tuple[bool, str | None]:
    """Keep one malformed evidence document from aborting the whole batch."""

    if not isinstance(entry, dict):
        return False, "native_case_evidence_not_an_object"
    try:
        return qualification(
            entry,
            benchmark="OSWorld",
            source_task_id=source_task_id,
        )
    except Exception as exc:
        return False, f"native_case_evidence_validation_error:{type(exc).__name__}"


def inspect_osworld_provider_containers(
    vm_path: Path,
    *,
    docker_cli: str | None = None,
    command_runner: Any = None,
) -> dict[str, Any]:
    """Read current containers and identify official OSWorld VM providers."""

    docker_cli = docker_cli or shutil.which("docker")
    command_runner = command_runner or subprocess.run
    result: dict[str, Any] = {
        "probe_succeeded": False,
        "docker_cli_found": bool(docker_cli),
        "docker_context": "",
        "official_container_ids": [],
        "provider_container_ids": [],
        "containers": [],
        "containers_disappeared_during_inspect": [],
    }
    if not docker_cli:
        result["error"] = "docker_cli_missing"
        return result
    try:
        context = command_runner(
            [docker_cli, "context", "show"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        listed = command_runner(
            [
                docker_cli, "container", "ls", "--all", "--quiet", "--no-trunc",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = type(exc).__name__
        return result
    docker_context = context.stdout.strip() if context.returncode == 0 else ""
    if not docker_context:
        result["error"] = (
            context.stderr or context.stdout or f"exit_{context.returncode}"
        ).strip()[-300:]
        return result
    result["docker_context"] = docker_context
    if listed.returncode != 0:
        result["error"] = (
            listed.stderr or listed.stdout or f"exit_{listed.returncode}"
        ).strip()[-300:]
        return result
    container_ids = [value.strip() for value in listed.stdout.splitlines() if value.strip()]
    if (
        len(container_ids) != len(set(container_ids))
        or any(not _is_sha256(container_id) for container_id in container_ids)
    ):
        result["error"] = "docker_list_returned_ambiguous_or_truncated_container_id"
        return result
    if not container_ids:
        result["probe_succeeded"] = True
        return result
    records: list[dict[str, Any]] = []
    disappeared: list[str] = []
    for container_id in container_ids:
        try:
            inspected = command_runner(
                [docker_cli, "container", "inspect", container_id],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            result["error"] = type(exc).__name__
            return result
        if inspected.returncode != 0:
            detail = (
                inspected.stderr
                or inspected.stdout
                or f"exit_{inspected.returncode}"
            ).strip()
            if "no such container" in detail.casefold():
                try:
                    relist_context = command_runner(
                        [docker_cli, "context", "show"],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=20,
                    )
                    relisted = command_runner(
                        [
                            docker_cli, "container", "ls", "--all", "--quiet",
                            "--no-trunc",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=20,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    result["error"] = f"docker_disappearance_recheck_{type(exc).__name__}"
                    return result
                relist_context_value = (
                    relist_context.stdout.strip()
                    if relist_context.returncode == 0
                    else ""
                )
                if relist_context_value != docker_context:
                    result["error"] = "docker_context_changed_during_container_inspect"
                    return result
                if relisted.returncode != 0:
                    result["error"] = (
                        relisted.stderr
                        or relisted.stdout
                        or f"exit_{relisted.returncode}"
                    ).strip()[-300:]
                    return result
                relisted_ids = [
                    value.strip()
                    for value in relisted.stdout.splitlines()
                    if value.strip()
                ]
                if (
                    len(relisted_ids) != len(set(relisted_ids))
                    or any(not _is_sha256(value) for value in relisted_ids)
                ):
                    result["error"] = (
                        "docker_disappearance_recheck_ambiguous_or_truncated_container_id"
                    )
                    return result
                if container_id in relisted_ids:
                    result["error"] = "docker_inspect_failed_but_container_still_present"
                    return result
                disappeared.append(container_id)
                continue
            result["error"] = detail[-300:]
            return result
        try:
            inspected_records = json.loads(inspected.stdout)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            result["error"] = type(exc).__name__
            return result
        if (
            not isinstance(inspected_records, list)
            or len(inspected_records) != 1
            or not isinstance(inspected_records[0], dict)
            or inspected_records[0].get("Id") != container_id
        ):
            result["error"] = "docker_single_inspect_invalid"
            return result
        records.append(inspected_records[0])

    official_ids: list[str] = []
    provider_ids: list[str] = []
    containers: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or record.get("Image") != OFFICIAL_OSWORLD_DOCKER_IMAGE_ID:
            continue
        container_id = str(record.get("Id") or "")
        if not container_id:
            continue
        mounts = record.get("Mounts") if isinstance(record.get("Mounts"), list) else []
        mounts_target_vm = any(
            isinstance(mount, dict)
            and mount.get("Destination") == "/System.qcow2"
            and docker_bind_source_matches_file(mount.get("Source"), vm_path)
            for mount in mounts
        )
        state = record.get("State") if isinstance(record.get("State"), dict) else {}
        official_ids.append(container_id)
        if mounts_target_vm:
            provider_ids.append(container_id)
        containers.append({
            "container_id": container_id,
            "name": str(record.get("Name") or "").lstrip("/"),
            "running": state.get("Running") is True,
            "status": str(state.get("Status") or ""),
            "mounts_target_vm": mounts_target_vm,
        })
    result.update({
        "probe_succeeded": True,
        "official_container_ids": sorted(official_ids),
        "provider_container_ids": sorted(provider_ids),
        "containers": sorted(containers, key=lambda item: item["container_id"]),
        "containers_disappeared_during_inspect": sorted(disappeared),
    })
    return result


def _docker_daemon_identity(info: Any) -> dict[str, str]:
    if not isinstance(info, dict):
        return {}
    return {
        "id": str(info.get("ID") or ""),
        "name": str(info.get("Name") or ""),
        "server_version": str(info.get("ServerVersion") or ""),
        "docker_root_dir": str(info.get("DockerRootDir") or ""),
        "os_type": str(info.get("OSType") or ""),
        "architecture": str(info.get("Architecture") or ""),
    }


def probe_docker_cli_daemon_identity(
    *,
    docker_cli: str | None = None,
    command_runner: Any = None,
) -> dict[str, Any]:
    """Read the CLI context and stable identity of the daemon it targets."""

    docker_cli = docker_cli or shutil.which("docker")
    command_runner = command_runner or subprocess.run
    result: dict[str, Any] = {
        "probe_succeeded": False,
        "docker_cli_found": bool(docker_cli),
        "context": "",
        "daemon_identity": {},
    }
    if not docker_cli:
        result["error"] = "docker_cli_missing"
        return result
    try:
        context = command_runner(
            [docker_cli, "context", "show"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        info = command_runner(
            [docker_cli, "info", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = type(exc).__name__
        return result
    if context.returncode != 0 or info.returncode != 0:
        failed = context if context.returncode != 0 else info
        result["error"] = (
            failed.stderr or failed.stdout or f"exit_{failed.returncode}"
        ).strip()[-300:]
        return result
    try:
        daemon_info = json.loads(info.stdout)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        result["error"] = type(exc).__name__
        return result
    identity = _docker_daemon_identity(daemon_info)
    result.update({
        "probe_succeeded": bool(context.stdout.strip()) and all(identity.values()),
        "context": context.stdout.strip(),
        "daemon_identity": identity,
        "docker_host_environment_set": bool(os.environ.get("DOCKER_HOST")),
    })
    return result


def probe_docker_sdk_provider(
    vm_path: Path,
    *,
    kvm_available: bool,
    client_factory: Any = None,
) -> dict[str, Any]:
    """Use the upstream provider's docker.from_env path and a disposable bind probe."""

    result: dict[str, Any] = {
        "probe_succeeded": False,
        "ping_succeeded": False,
        "daemon_identity": {},
        "client_base_url": "",
        "image_identities": {},
        "minimal_container_probe": {
            "attempted": False,
            "created": False,
            "container_id": "",
            "mount_read_only": False,
            "exit_code": None,
            "kvm_expected": kvm_available,
            "cleanup_attempted": False,
            "cleanup_succeeded": False,
            "residual_container_present": False,
        },
    }
    client = None
    container = None
    try:
        if client_factory is None:
            import docker

            client = docker.from_env()
        else:
            client = client_factory()
        result["client_base_url"] = str(getattr(getattr(client, "api", None), "base_url", ""))
        result["ping_succeeded"] = client.ping() is True
        result["daemon_identity"] = _docker_daemon_identity(client.info())
        image_references = {
            "untagged": OSWORLD_DOCKER_IMAGE,
            "digest": OFFICIAL_OSWORLD_DOCKER_IMAGE,
            "latest": f"{OSWORLD_DOCKER_IMAGE}:latest",
        }
        result["image_identities"] = {
            name: str(client.images.get(reference).id or "")
            for name, reference in image_references.items()
        }

        probe = result["minimal_container_probe"]
        probe["attempted"] = True
        devices = ["/dev/kvm:/dev/kvm:rwm"] if kvm_available else []
        kvm_command = "test -c /dev/kvm" if kvm_available else 'test "$KVM" = N'
        container = client.containers.create(
            OSWORLD_DOCKER_IMAGE,
            command=[
                "-c",
                f"test -s /System.qcow2 && {kvm_command}",
            ],
            entrypoint="sh",
            environment={
                "KVM": "Y" if kvm_available else "N",
            },
            devices=devices,
            volumes={
                str(vm_path.resolve()): {
                    "bind": "/System.qcow2",
                    "mode": "ro",
                }
            },
        )
        probe["created"] = True
        probe["container_id"] = str(container.id or "")
        container.reload()
        mounts = (
            container.attrs.get("Mounts")
            if isinstance(container.attrs, dict)
            and isinstance(container.attrs.get("Mounts"), list)
            else []
        )
        probe["mount_read_only"] = any(
            isinstance(mount, dict)
            and mount.get("Type") == "bind"
            and mount.get("Destination") == "/System.qcow2"
            and mount.get("RW") is False
            and docker_bind_source_matches_file(mount.get("Source"), vm_path)
            for mount in mounts
        )
        container.start()
        wait_result = container.wait(timeout=60)
        probe["exit_code"] = (
            wait_result.get("StatusCode")
            if isinstance(wait_result, dict)
            else wait_result
        )
        logs = container.logs(stdout=True, stderr=True)
        if isinstance(logs, bytes):
            logs = logs.decode("utf-8", errors="replace")
        probe["detail"] = str(logs or "")[-300:]
    except Exception as exc:
        result["error"] = type(exc).__name__
    finally:
        probe = result["minimal_container_probe"]
        if container is not None:
            probe["cleanup_attempted"] = True
            try:
                container.remove(force=True, v=True)
                probe["cleanup_succeeded"] = True
            except Exception as exc:
                probe["cleanup_detail"] = type(exc).__name__
            try:
                residual = client.containers.list(
                    all=True,
                    filters={"id": probe["container_id"]},
                )
                probe["residual_container_present"] = bool(residual)
            except Exception as exc:
                probe["residual_container_present"] = True
                probe["residual_probe_detail"] = type(exc).__name__
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    probe = result["minimal_container_probe"]
    image_ids = result.get("image_identities") or {}
    checks = {
        "ping_succeeded": result.get("ping_succeeded") is True,
        "daemon_identity_complete": all((result.get("daemon_identity") or {}).values()),
        "official_images_match": (
            set(image_ids) == {"untagged", "digest", "latest"}
            and all(value == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID for value in image_ids.values())
        ),
        "minimal_container_created": probe.get("created") is True,
        "exact_vm_file_bind_read_only": probe.get("mount_read_only") is True,
        "kvm_or_tcg_probe_succeeded": probe.get("exit_code") == 0,
        "minimal_container_cleanup_succeeded": (
            probe.get("cleanup_attempted") is True
            and probe.get("cleanup_succeeded") is True
            and probe.get("residual_container_present") is False
        ),
    }
    result["checks"] = checks
    result["probe_succeeded"] = all(checks.values())
    return result


def docker_cli_sdk_daemon_match(
    cli_probe: dict[str, Any],
    sdk_probe: dict[str, Any],
) -> bool:
    """Bind Docker CLI asset checks to docker.from_env's actual daemon."""

    cli_identity = cli_probe.get("daemon_identity") or {}
    sdk_identity = sdk_probe.get("daemon_identity") or {}
    identity_keys = {
        "id", "name", "server_version", "docker_root_dir", "os_type", "architecture"
    }
    return all((
        cli_probe.get("probe_succeeded") is True,
        sdk_probe.get("probe_succeeded") is True,
        all(cli_identity.get(key) for key in identity_keys),
        all(sdk_identity.get(key) for key in identity_keys),
        all(cli_identity.get(key) == sdk_identity.get(key) for key in identity_keys),
    ))


def docker_provider_identity_stable(
    preflight_cli: dict[str, Any],
    preflight_sdk: dict[str, Any],
    postflight_cli: dict[str, Any],
    postflight_sdk: dict[str, Any],
) -> bool:
    """Reject a daemon/context switch between collection preflight and postflight."""

    pre_cli_identity = preflight_cli.get("daemon_identity") or {}
    pre_sdk_identity = preflight_sdk.get("daemon_identity") or {}
    post_cli_identity = postflight_cli.get("daemon_identity") or {}
    post_sdk_identity = postflight_sdk.get("daemon_identity") or {}
    pre_base_url = preflight_sdk.get("client_base_url")
    post_base_url = postflight_sdk.get("client_base_url")
    pre_context = preflight_cli.get("context")
    post_context = postflight_cli.get("context")
    return all((
        docker_cli_sdk_daemon_match(preflight_cli, preflight_sdk),
        docker_cli_sdk_daemon_match(postflight_cli, postflight_sdk),
        pre_cli_identity == post_cli_identity,
        pre_sdk_identity == post_sdk_identity,
        isinstance(pre_context, str),
        bool(pre_context),
        pre_context == post_context,
        isinstance(pre_base_url, str),
        bool(pre_base_url),
        pre_base_url == post_base_url,
        preflight_sdk.get("image_identities") == postflight_sdk.get("image_identities"),
    ))


def cleanup_timeout_provider_containers(
    before_probe: dict[str, Any],
    vm_path: Path,
    *,
    inspect_fn: Any = None,
) -> dict[str, Any]:
    """Audit possible timeout residue without claiming or deleting containers."""

    inspect_fn = inspect_fn or inspect_osworld_provider_containers
    after_probe = inspect_fn(vm_path)
    before_ids = set(before_probe.get("provider_container_ids") or [])
    after_ids = set(after_probe.get("provider_container_ids") or [])
    suspected_ids = (
        sorted(after_ids - before_ids)
        if before_probe.get("probe_succeeded") and after_probe.get("probe_succeeded")
        else []
    )
    return {
        "trigger": "native_case_timeout",
        "passed": all((
            before_probe.get("probe_succeeded") is True,
            after_probe.get("probe_succeeded") is True,
            not suspected_ids,
        )),
        "batch_continuation_allowed": False,
        "destructive_cleanup_permitted": False,
        "cleanup_attempted": False,
        "ownership_proven": False,
        "before_probe": before_probe,
        "after_timeout_probe": after_probe,
        "suspected_new_provider_container_ids": suspected_ids,
        "manual_cleanup_required": bool(suspected_ids),
        "reason": "provider_containers_lack_unique_batch_case_ownership_label",
    }


def inspect_provider_containers_under_lock(
    vm_path: Path,
    *,
    timeout_seconds: float,
    inspect_fn: Any = None,
) -> dict[str, Any]:
    """Read provider containers while no OSWorld lifecycle can be in flight."""

    inspect_fn = inspect_fn or inspect_osworld_provider_containers
    lock_path = osworld_provider_lock_path(vm_path)
    lock = FileLock(str(lock_path))
    result: dict[str, Any] = {
        "lock_path": str(lock_path),
        "lock_acquired": False,
        "probe_succeeded": False,
        "official_container_ids": [],
        "provider_container_ids": [],
    }
    try:
        lock.acquire(timeout=max(0.0, timeout_seconds))
    except Timeout:
        result["error"] = "provider_vm_lock_timeout"
        return result
    result["lock_acquired"] = True
    try:
        probe = inspect_fn(vm_path)
        if not isinstance(probe, dict):
            result["error"] = "provider_container_probe_not_an_object"
            return result
        result.update(probe)
        result["lock_acquired"] = True
        return result
    except Exception as exc:
        result["error"] = type(exc).__name__
        return result
    finally:
        lock.release()


def provider_containers_absent(probe: dict[str, Any]) -> bool:
    return all((
        probe.get("lock_acquired") is True,
        probe.get("probe_succeeded") is True,
        probe.get("official_container_ids") == [],
        probe.get("provider_container_ids") == [],
    ))


def infrastructure_failure_retryable(
    entry: dict[str, Any] | None,
    *,
    return_code: int | None,
    process_failure: str | None,
) -> bool:
    """Classify only launch/provider failures for a bounded retry."""

    if process_failure is not None:
        return True
    if entry is None:
        return return_code != 0
    failure = entry.get("failure")
    failure_text = ""
    if isinstance(failure, dict):
        failure_text = " ".join(
            str(failure.get(name) or "") for name in ("type", "message", "traceback")
        ).casefold()
    retry_markers = (
        "timeout", "notfound", "docker", "container", "connection",
        "apierror", "readiness", "provider", "daemon",
    )
    return any(marker in failure_text for marker in retry_markers)


def _tail_text(value: Any, limit: int = 4000) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value or "")[-limit:]


def live_provider_postflight_valid(
    provider_probe: Any,
    kvm_probe: dict[str, Any],
    container_probe: dict[str, Any],
) -> bool:
    """Require a healthy provider and zero residual official desktop containers."""

    return all((
        live_provider_preflight_valid(provider_probe, kvm_probe),
        container_probe.get("probe_succeeded") is True,
        container_probe.get("official_container_ids") == [],
        container_probe.get("provider_container_ids") == [],
    ))


def reusable_evidence(
    entry: dict[str, Any],
    case: Any,
    *,
    attestation_path: Path,
    vm_path: Path,
    bootstrap_report_path: Path,
    environment_lock_path: Path,
    current_provider_details: dict[str, Any],
    upstream_git_binding: dict[str, Any],
) -> bool:
    try:
        qualified, _ = qualify_entry_safely(
            entry,
            source_task_id=case.source_task_id,
        )
        if not all((
            qualified,
            evidence_matches_current_case(
                entry,
                case,
                attestation_path=attestation_path,
                vm_path=vm_path,
                bootstrap_report_path=bootstrap_report_path,
                environment_lock_path=environment_lock_path,
                current_provider_details=current_provider_details,
                upstream_git_binding=upstream_git_binding,
            ),
        )):
            return False
        return True
    except Exception:
        return False


def evidence_matches_current_case(
    entry: dict[str, Any],
    case: Any,
    *,
    attestation_path: Path,
    vm_path: Path,
    bootstrap_report_path: Path,
    environment_lock_path: Path,
    current_provider_details: dict[str, Any],
    upstream_git_binding: dict[str, Any],
) -> bool:
    """Bind both resumed and fresh evidence to every current case input."""

    try:
        if not all((
            attestation_path.is_file(),
            vm_path.is_file(),
            bootstrap_report_path.is_file(),
            environment_lock_path.is_file(),
            entry.get("case_id") == case.case_id,
            entry.get("source_task_id") == case.source_task_id,
            entry.get("official_task_config_sha256") == case.config_sha256,
            entry.get("official_evaluator_source_sha256")
            == case.dispatch.evaluator_sha256,
            upstream_git_binding.get("probe_succeeded") is True,
            upstream_git_binding.get("tracked_tree_clean") is True,
            upstream_git_binding.get("revision") == case.upstream_revision,
        )):
            return False
        evaluator_probe = entry.get("evaluator_probe")
        setup_probe = entry.get("setup_probe")
        provider = entry.get("provider_preflight")
        if not all(isinstance(value, dict) for value in (
            evaluator_probe, setup_probe, provider
        )):
            return False
        provider_details = provider.get("details")
        setup_calls = setup_probe.get("calls")
        if not isinstance(provider_details, dict) or not isinstance(setup_calls, list):
            return False

        task_setup = case.task.get("config", [])
        evaluator = case.task.get("evaluator")
        if not isinstance(evaluator, dict):
            return False
        evaluator_postconfig = evaluator.get("postconfig", [])
        expected_phases = {
            "first_reset_task_setup": (
                len(task_setup), canonical_case_digest(task_setup)
            ),
            "official_evaluator_postconfig": (
                len(evaluator_postconfig), canonical_case_digest(evaluator_postconfig)
            ),
            "second_reset_task_setup": (
                len(task_setup), canonical_case_digest(task_setup)
            ),
        }
        phase_bindings_valid = all(
            len(phase_calls := [
                call
                for call in setup_calls
                if isinstance(call, dict) and call.get("phase") == phase
            ]) == 1
            and phase_calls[0].get("config_count") == expected_count
            and phase_calls[0].get("config_sha256") == expected_sha256
            for phase, (expected_count, expected_sha256) in expected_phases.items()
        )
        return all((
            evaluator_probe.get("task_evaluator_sha256")
            == canonical_case_digest(evaluator),
            evaluator_probe.get("evaluator_func") == evaluator.get("func"),
            phase_bindings_valid,
            all(_is_sha256(current_provider_details.get(name)) for name in (
                "factory_sha256", "provider_source_sha256", "manager_source_sha256",
            )),
            provider_details.get("asset_attestation_sha256")
            == file_sha256(attestation_path),
            provider_details.get("python_bootstrap_report_sha256")
            == file_sha256(bootstrap_report_path),
            provider_details.get("python_environment_lock_sha256")
            == file_sha256(environment_lock_path),
            provider_details.get("factory_sha256")
            == current_provider_details.get("factory_sha256"),
            provider_details.get("provider_source_sha256")
            == current_provider_details.get("provider_source_sha256"),
            provider_details.get("manager_source_sha256")
            == current_provider_details.get("manager_source_sha256"),
            Path(str(provider_details.get("vm_disk_path") or "")).resolve()
            == vm_path.resolve(),
        ))
    except Exception:
        return False


def exact_full_collection_selected(
    *,
    full_collection_requested: bool,
    discovered_case_count: int,
    unique_case_count: int,
    selected_case_count: int,
) -> bool:
    """Return true only for the complete, duplicate-free 91-case collection."""

    return all((
        full_collection_requested,
        discovered_case_count == EXPECTED_OSWORLD_CASE_COUNT,
        unique_case_count == EXPECTED_OSWORLD_CASE_COUNT,
        selected_case_count == EXPECTED_OSWORLD_CASE_COUNT,
    ))


def live_provider_preflight_valid(provider_probe: Any, kvm_probe: dict[str, Any]) -> bool:
    """Apply the native profile's live Docker and KVM/TCG resume gate."""

    details = provider_probe.details or {}
    kvm_available = kvm_probe.get("device_available")
    kvm_exit = kvm_probe.get("exit_code")
    kvm_result_valid = (
        isinstance(kvm_available, bool)
        and (
            (
                isinstance(kvm_exit, int)
                and not isinstance(kvm_exit, bool)
                and ((kvm_exit == 0) is kvm_available)
            )
            or (kvm_exit is None and kvm_available is False)
        )
    )
    return all((
        provider_probe.provider == "docker",
        provider_probe.configuration_resolved is True,
        provider_probe.launch_ready is True,
        not provider_probe.blockers,
        details.get("daemon_reachable") is True,
        details.get("docker_image_present") is True,
        details.get("docker_digest_image_present") is True,
        details.get("docker_latest_image_present") is True,
        details.get("vm_disk_present") is True,
        details.get("asset_attestation_verified") is True,
        details.get("python_bootstrap_verified") is True,
        kvm_probe.get("attempted") is True,
        kvm_result_valid,
    ))


def run_locked_provider_runtime_probes(
    vm_path: Path,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Serialize transient KVM/SDK probes with every real OSWorld VM lifecycle."""

    lock_path = osworld_provider_lock_path(vm_path)
    lock = FileLock(str(lock_path))
    result: dict[str, Any] = {
        "lock_path": str(lock_path),
        "lock_acquired": False,
    }
    try:
        lock.acquire(timeout=max(0.0, timeout_seconds))
    except Timeout:
        result["error"] = "provider_vm_lock_timeout"
        return result
    result["lock_acquired"] = True
    try:
        kvm_probe = probe_docker_kvm_device(OSWORLD_DOCKER_IMAGE)
        result.update({
            "kvm_probe": kvm_probe,
            "docker_cli_daemon": probe_docker_cli_daemon_identity(),
            "docker_sdk_provider": probe_docker_sdk_provider(
                vm_path,
                kvm_available=kvm_probe.get("device_available") is True,
            ),
            "container_probe": inspect_osworld_provider_containers(vm_path),
        })
        return result
    finally:
        lock.release()


def _main_unlocked() -> int:
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case-id", action="append", default=[])
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--source-native-root", default="artifacts/source-native-v4")
    parser.add_argument("--upstream-root", default="upstream/osworld")
    parser.add_argument(
        "--path-to-vm",
        default=DEFAULT_OSWORLD_VM_PATH,
    )
    parser.add_argument(
        "--asset-attestation",
        default="artifacts/native-runtime-v4/osworld-assets/asset_attestation.json",
    )
    parser.add_argument(
        "--bootstrap-report",
        default=".venv-osworld-native/osworld-native-bootstrap-report.json",
    )
    parser.add_argument(
        "--environment-lock",
        default="configs/osworld-native-requirements.lock",
    )
    parser.add_argument(
        "--output", default="artifacts/native-runtime-v4/osworld-native"
    )
    parser.add_argument("--output-lock-timeout-seconds", type=float, default=0.0)
    parser.add_argument("--provider-lock-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=3.0)
    parser.add_argument("--rerun-valid", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--timeout-seconds", type=int, default=0,
        help="0 disables the outer timeout so the launcher can always run its cleanup",
    )
    args = parser.parse_args()
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1")
    if args.retry_backoff_seconds < 0:
        parser.error("--retry-backoff-seconds cannot be negative")

    output = (ROOT / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_root = (ROOT / args.source_native_root).resolve()
    upstream_root = (ROOT / args.upstream_root).resolve()
    cases = load_osworld_cases(
        ROOT, source_native_root=source_root, upstream_root=upstream_root
    )
    by_id = {case.case_id: case for case in cases}
    requested = list(by_id) if args.all else list(dict.fromkeys(args.case_id))
    unknown = sorted(set(requested) - set(by_id))
    if unknown:
        raise SystemExit("unknown OSWorld case id(s): " + ",".join(unknown))
    all_91_selected = exact_full_collection_selected(
        full_collection_requested=args.all,
        discovered_case_count=len(cases),
        unique_case_count=len(by_id),
        selected_case_count=len(requested),
    )
    selection_details = {
        "full_collection_requested": args.all,
        "expected_full_collection_count": EXPECTED_OSWORLD_CASE_COUNT,
        "discovered_case_count": len(cases),
        "unique_case_count": len(by_id),
        "selected_case_count": len(requested),
        "all_91_selected": all_91_selected,
        # Retained for report readers that consumed the original field.  Its
        # value is now the validated selection claim, never just argv state.
        "all_91_explicitly_selected": all_91_selected,
        "full_collection_validated": False,
    }
    if args.all and not all_91_selected:
        report = {
            "schema_version": "osworld-native-batch-v1",
            "status": "blocked_full_collection_selection",
            **selection_details,
            "native_environment_validated_count": 0,
            "failed_count": len(requested),
            "execution_mode": "sequential",
            "registry_merged": False,
            "atomic_sync_required": False,
            "results": [],
        }
        write_json(output / "batch_report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    vm_path = (ROOT / args.path_to_vm).resolve()
    attestation_path = (ROOT / args.asset_attestation).resolve()
    bootstrap_report_path = (ROOT / args.bootstrap_report).resolve()
    environment_lock_path = (ROOT / args.environment_lock).resolve()
    bootstrap_valid, bootstrap_blockers, bootstrap_details = (
        validate_osworld_python_bootstrap(
            bootstrap_report_path,
            environment_lock_path,
            upstream_root,
        )
    )
    python_runtime = {
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "isolated": bootstrap_details.get("python_environment_isolated") is True,
        "bootstrap_report_path": str(bootstrap_report_path),
        "bootstrap_report_sha256": bootstrap_details.get(
            "python_bootstrap_report_sha256", ""
        ),
        "environment_lock_path": str(environment_lock_path),
        "environment_lock_sha256": bootstrap_details.get(
            "python_environment_lock_sha256", ""
        ),
    }
    if not bootstrap_valid:
        report = {
            "schema_version": "osworld-native-batch-v1",
            "status": "blocked_python_bootstrap",
            **selection_details,
            "native_environment_validated_count": 0,
            "failed_count": len(requested),
            "execution_mode": "sequential",
            "python_runtime": python_runtime,
            "bootstrap_blockers": bootstrap_blockers,
            "registry_merged": False,
            "atomic_sync_required": False,
            "results": [],
        }
        write_json(output / "batch_report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    provider_probe = probe_real_vm_provider(
        upstream_root,
        provider="docker",
        path_to_vm=vm_path,
        docker_image=OSWORLD_DOCKER_IMAGE,
        asset_attestation=attestation_path,
        bootstrap_report=bootstrap_report_path,
        environment_lock=environment_lock_path,
    )
    upstream_git_binding = probe_upstream_git_binding(upstream_root)
    current_provider_details = (
        provider_probe.details if isinstance(provider_probe.details, dict) else {}
    )
    selected_revisions_match = all(
        case.upstream_revision == upstream_git_binding.get("revision")
        for case in (by_id[case_id] for case_id in requested)
    )
    preflight_runtime_probes = run_locked_provider_runtime_probes(
        vm_path,
        timeout_seconds=args.provider_lock_timeout_seconds,
    )
    kvm_probe = preflight_runtime_probes.get("kvm_probe") or {}
    cli_daemon_probe = preflight_runtime_probes.get("docker_cli_daemon") or {}
    sdk_provider_probe = preflight_runtime_probes.get("docker_sdk_provider") or {}
    preflight_container_probe = preflight_runtime_probes.get("container_probe") or {}
    daemon_identity_matches = docker_cli_sdk_daemon_match(
        cli_daemon_probe,
        sdk_provider_probe,
    )
    live_preflight_validated = all((
        live_provider_postflight_valid(
            provider_probe,
            kvm_probe,
            preflight_container_probe,
        ),
        daemon_identity_matches,
        upstream_git_binding.get("probe_succeeded") is True,
        selected_revisions_match,
        all(_is_sha256(current_provider_details.get(name)) for name in (
            "factory_sha256", "provider_source_sha256", "manager_source_sha256",
        )),
    ))
    live_preflight = {
        "validated": live_preflight_validated,
        "provider": provider_probe.as_dict(),
        "upstream_git_binding": upstream_git_binding,
        "selected_case_revisions_match": selected_revisions_match,
        "kvm_probe": kvm_probe,
        "docker_cli_daemon": cli_daemon_probe,
        "docker_sdk_provider": sdk_provider_probe,
        "daemon_identity_matches": daemon_identity_matches,
        "container_probe": preflight_container_probe,
        "provider_vm_lock": {
            "path": preflight_runtime_probes.get("lock_path", ""),
            "acquired": preflight_runtime_probes.get("lock_acquired") is True,
            "error": preflight_runtime_probes.get("error", ""),
        },
    }
    if not live_preflight_validated:
        report = {
            "schema_version": "osworld-native-batch-v1",
            "status": "blocked_live_provider_preflight",
            **selection_details,
            "native_environment_validated_count": 0,
            "failed_count": len(requested),
            "execution_mode": "sequential",
            "python_runtime": python_runtime,
            "live_provider_preflight": live_preflight,
            "registry_merged": False,
            "atomic_sync_required": False,
            "results": [],
        }
        write_json(output / "batch_report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    launcher = ROOT / "scripts" / "run_osworld_native_case.py"
    results: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    stop_collection = False
    for case_id in requested:
        case = by_id[case_id]
        evidence_path = output / "cases" / f"{case_id}.json"
        if evidence_path.is_file() and not args.rerun_valid:
            try:
                existing_entry = json.loads(evidence_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                existing_entry = None
            if (
                isinstance(existing_entry, dict)
                and reusable_evidence(
                    existing_entry,
                    case,
                    attestation_path=attestation_path,
                    vm_path=vm_path,
                    bootstrap_report_path=bootstrap_report_path,
                    environment_lock_path=environment_lock_path,
                    current_provider_details=current_provider_details,
                    upstream_git_binding=upstream_git_binding,
                )
            ):
                accepted.append(existing_entry)
                results.append({
                    "case_id": case_id,
                    "return_code": 0,
                    "status": existing_entry["status"],
                    "qualified": True,
                    "reason": None,
                    "evidence_path": str(evidence_path),
                    "evidence_file_sha256": file_sha256(evidence_path),
                    "skipped_already_valid": True,
                    "duration_seconds": 0.0,
                })
                continue
        command = [
            sys.executable,
            str(launcher),
            "--case-id", case_id,
            "--source-native-root", str(source_root),
            "--upstream-root", str(upstream_root),
            "--provider", "docker",
            "--path-to-vm", str(vm_path),
            "--asset-attestation", str(attestation_path),
            "--bootstrap-report", str(bootstrap_report_path),
            "--environment-lock", str(environment_lock_path),
            "--provider-lock-timeout-seconds",
            str(args.provider_lock_timeout_seconds),
            "--output", str(evidence_path),
        ]
        if args.headless:
            command.append("--headless")
        case_started = time.monotonic()
        attempts: list[dict[str, Any]] = []
        entry: dict[str, Any] | None = None
        qualified = False
        reason: str | None = "native_case_evidence_missing"
        return_code: int | None = None
        process_failure: str | None = None
        timeout_cleanup: dict[str, Any] | None = None
        stdout_tail = ""
        stderr_tail = ""
        for attempt_number in range(1, args.max_attempts + 1):
            attempt_started = time.monotonic()
            container_baseline = inspect_provider_containers_under_lock(
                vm_path,
                timeout_seconds=args.provider_lock_timeout_seconds,
            )
            if not provider_containers_absent(container_baseline):
                process_failure = "provider_container_baseline_residual_or_unknown"
                return_code = None
                stdout_tail = ""
                stderr_tail = ""
                post_case_probe = container_baseline
                entry = None
                qualified = False
                reason = process_failure
            else:
                try:
                    completed = subprocess.run(
                        command,
                        cwd=ROOT,
                        env=utf8_subprocess_environment(),
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        timeout=(
                            args.timeout_seconds if args.timeout_seconds > 0 else None
                        ),
                    )
                    return_code = completed.returncode
                    process_failure = None
                    stdout_tail = _tail_text(completed.stdout)
                    stderr_tail = _tail_text(completed.stderr)
                except subprocess.TimeoutExpired as exc:
                    return_code = None
                    process_failure = "native_case_timeout"
                    stdout_tail = _tail_text(exc.stdout)
                    stderr_tail = _tail_text(exc.stderr)
                except (OSError, subprocess.SubprocessError) as exc:
                    return_code = None
                    process_failure = (
                        f"native_case_process_exception:{type(exc).__name__}"
                    )
                    stdout_tail = ""
                    stderr_tail = _tail_text(str(exc))

                entry = None
                if evidence_path.is_file():
                    try:
                        candidate = json.loads(evidence_path.read_text(encoding="utf-8"))
                        if isinstance(candidate, dict):
                            entry = candidate
                    except (OSError, ValueError, json.JSONDecodeError):
                        entry = None
                qualified = False
                reason = process_failure or "native_case_evidence_missing"
                if entry is not None:
                    qualified, reason = qualify_entry_safely(
                        entry,
                        source_task_id=case.source_task_id,
                    )
                    if qualified and not evidence_matches_current_case(
                        entry,
                        case,
                        attestation_path=attestation_path,
                        vm_path=vm_path,
                        bootstrap_report_path=bootstrap_report_path,
                        environment_lock_path=environment_lock_path,
                        current_provider_details=current_provider_details,
                        upstream_git_binding=upstream_git_binding,
                    ):
                        qualified = False
                        reason = "native_case_evidence_current_binding_mismatch"
                    if return_code != 0:
                        qualified = False
                        reason = reason or f"launcher_exit_{return_code}"

                post_case_probe = inspect_provider_containers_under_lock(
                    vm_path,
                    timeout_seconds=args.provider_lock_timeout_seconds,
                )

            provider_clean = provider_containers_absent(post_case_probe)
            cleanup_evidence = (
                entry.get("provider_cleanup_verification")
                if isinstance(entry, dict)
                and isinstance(entry.get("provider_cleanup_verification"), dict)
                else None
            )
            cleanup_evidence_failed = (
                cleanup_evidence is not None
                and cleanup_evidence.get("passed") is not True
            )
            if not provider_clean or cleanup_evidence_failed:
                qualified = False
                reason = "provider_cleanup_residual_or_unknown"
            if process_failure == "native_case_timeout":
                timeout_cleanup = cleanup_timeout_provider_containers(
                    container_baseline,
                    vm_path,
                    inspect_fn=lambda _path, value=post_case_probe: value,
                )

            retryable = infrastructure_failure_retryable(
                entry,
                return_code=return_code,
                process_failure=process_failure,
            )
            attempt_record = {
                "attempt": attempt_number,
                "return_code": return_code,
                "qualified": qualified,
                "reason": reason,
                "process_failure": process_failure,
                "duration_seconds": round(time.monotonic() - attempt_started, 3),
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
                "provider_container_baseline": container_baseline,
                "post_case_provider_probe": post_case_probe,
                "provider_cleanup_evidence": cleanup_evidence,
                "timeout_cleanup": timeout_cleanup,
                "retryable_infrastructure_failure": retryable,
            }
            attempts.append(attempt_record)
            if qualified:
                break
            if not provider_clean or cleanup_evidence_failed:
                stop_collection = True
                break
            if retryable and attempt_number < args.max_attempts:
                if args.retry_backoff_seconds:
                    time.sleep(args.retry_backoff_seconds)
                continue
            if process_failure in {
                "native_case_timeout",
                "provider_container_baseline_residual_or_unknown",
            } or (process_failure or "").startswith("native_case_process_exception:"):
                stop_collection = True
            break

        if qualified and entry is not None:
            accepted.append(entry)
        results.append({
            "case_id": case_id,
            "return_code": return_code,
            "status": entry.get("status") if entry else "evidence_missing",
            "qualified": qualified,
            "reason": reason,
            "evidence_path": str(evidence_path),
            "evidence_file_sha256": (
                file_sha256(evidence_path) if evidence_path.is_file() else ""
            ),
            "skipped_already_valid": False,
            "duration_seconds": round(time.monotonic() - case_started, 3),
            "attempt_count": len(attempts),
            "attempts": attempts,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "timeout_cleanup": timeout_cleanup,
        })
        if stop_collection:
            break

    postflight_provider_probe = probe_real_vm_provider(
        upstream_root,
        provider="docker",
        path_to_vm=vm_path,
        docker_image=OSWORLD_DOCKER_IMAGE,
        asset_attestation=attestation_path,
        bootstrap_report=bootstrap_report_path,
        environment_lock=environment_lock_path,
    )
    postflight_runtime_probes = run_locked_provider_runtime_probes(
        vm_path,
        timeout_seconds=args.provider_lock_timeout_seconds,
    )
    postflight_kvm_probe = postflight_runtime_probes.get("kvm_probe") or {}
    postflight_cli_daemon_probe = (
        postflight_runtime_probes.get("docker_cli_daemon") or {}
    )
    postflight_sdk_provider_probe = (
        postflight_runtime_probes.get("docker_sdk_provider") or {}
    )
    postflight_container_probe = postflight_runtime_probes.get("container_probe") or {}
    postflight_daemon_identity_matches = docker_cli_sdk_daemon_match(
        postflight_cli_daemon_probe,
        postflight_sdk_provider_probe,
    )
    provider_identity_stable = docker_provider_identity_stable(
        cli_daemon_probe,
        sdk_provider_probe,
        postflight_cli_daemon_probe,
        postflight_sdk_provider_probe,
    )
    postflight_validated = all((
        live_provider_postflight_valid(
            postflight_provider_probe,
            postflight_kvm_probe,
            postflight_container_probe,
        ),
        postflight_daemon_identity_matches,
        provider_identity_stable,
    ))
    live_postflight = {
        "validated": postflight_validated,
        "provider": postflight_provider_probe.as_dict(),
        "kvm_probe": postflight_kvm_probe,
        "docker_cli_daemon": postflight_cli_daemon_probe,
        "docker_sdk_provider": postflight_sdk_provider_probe,
        "daemon_identity_matches": postflight_daemon_identity_matches,
        "preflight_postflight_identity_stable": provider_identity_stable,
        "container_probe": postflight_container_probe,
        "provider_vm_lock": {
            "path": postflight_runtime_probes.get("lock_path", ""),
            "acquired": postflight_runtime_probes.get("lock_acquired") is True,
            "error": postflight_runtime_probes.get("error", ""),
        },
    }
    full_collection_validated = all((
        all_91_selected,
        len(accepted) == EXPECTED_OSWORLD_CASE_COUNT,
        len(results) == EXPECTED_OSWORLD_CASE_COUNT,
        all(result["qualified"] is True for result in results),
        postflight_validated,
    ))
    batch_validated = all((
        len(accepted) == len(requested),
        bool(requested),
        postflight_validated,
    ))
    if args.all:
        batch_validated = batch_validated and full_collection_validated
    sync_authorized = full_collection_validated
    report = {
        "schema_version": "osworld-native-batch-v1",
        "status": (
            NATIVE_RUNTIME_READY_STATUS
            if sync_authorized
            else "native_collection_incomplete"
        ),
        **selection_details,
        "full_collection_validated": full_collection_validated,
        "native_environment_validated_count": len(accepted),
        "failed_count": len(requested) - len(accepted),
        "skipped_already_valid_count": sum(
            result["skipped_already_valid"] for result in results
        ),
        "execution_mode": "sequential",
        "python_runtime": python_runtime,
        "live_provider_preflight": live_preflight,
        "live_provider_postflight": live_postflight,
        "registry_merged": False,
        "atomic_sync_required": sync_authorized,
        "sync_command": (
            (
                "python scripts/sync_source_native_runtime.py --merge-evidence "
                + str(output)
                + " --require-ready-benchmark OSWorld"
            )
            if sync_authorized
            else None
        ),
        "status_required": NATIVE_RUNTIME_READY_STATUS,
        "results": results,
    }
    write_json(output / "batch_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if batch_validated else 1


def main() -> int:
    lock_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    lock_parser.add_argument(
        "--output",
        default="artifacts/native-runtime-v4/osworld-native",
    )
    lock_parser.add_argument(
        "--output-lock-timeout-seconds",
        type=float,
        default=0.0,
    )
    lock_args, _ = lock_parser.parse_known_args()
    output = (ROOT / lock_args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock_path = output / ".osworld-native-batch.lock"
    lock = FileLock(str(lock_path))
    try:
        lock.acquire(timeout=max(0.0, lock_args.output_lock_timeout_seconds))
    except Timeout:
        report = {
            "schema_version": "osworld-native-batch-v1",
            "status": "blocked_output_lock_held",
            "output_path": str(output),
            "output_lock_path": str(lock_path),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    try:
        return _main_unlocked()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
