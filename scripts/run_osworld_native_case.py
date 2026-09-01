"""Start one source-native OSWorld case with the real upstream DesktopEnv.

There is no local fallback in this entry point. Missing Python dependencies,
provider CLI/daemon, provider image, or VM disk are reported as blockers before
OSWorld can auto-download a large disk. A successful run performs upstream
``DesktopEnv.reset(task)``, executes the case's unchanged evaluator without a
terminal short circuit, marks the VM used with ``WAIT``, and proves a second
Docker-backed reset replaced the container.
"""

from __future__ import annotations

import argparse
import copy
import functools
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OSWORLD_VM_PATH = "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.osworld_runtime import (  # noqa: E402
    load_osworld_cases,
    osworld_provider_lock_path,
    probe_real_vm_provider,
)


PYTHON_UTF8_ENVIRONMENT = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8:backslashreplace",
}


def utf8_subprocess_environment(
    base_environment: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return an inherited environment whose Python stdio is always UTF-8."""

    environment = dict(os.environ if base_environment is None else base_environment)
    environment.update(PYTHON_UTF8_ENVIRONMENT)
    return environment


def configure_utf8_process_stdio(
    *,
    environment: dict[str, str] | None = None,
    stdout: Any = None,
    stderr: Any = None,
) -> dict[str, Any]:
    """Make this launcher and Python children Unicode-safe on Windows."""

    target_environment = os.environ if environment is None else environment
    target_environment.update(PYTHON_UTF8_ENVIRONMENT)
    streams = {
        "stdout": sys.stdout if stdout is None else stdout,
        "stderr": sys.stderr if stderr is None else stderr,
    }
    configured: dict[str, bool] = {}
    for name, stream in streams.items():
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
            configured[name] = True
        else:
            configured[name] = False
    return {
        "environment": dict(PYTHON_UTF8_ENVIRONMENT),
        "streams_reconfigured": configured,
    }


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


def observation_digest(observation: Any) -> str:
    if not isinstance(observation, dict):
        payload = repr(observation).encode("utf-8", errors="replace")
    else:
        screenshot = observation.get("screenshot")
        if isinstance(screenshot, bytes):
            screenshot_digest = hashlib.sha256(screenshot).hexdigest()
        else:
            screenshot_digest = hashlib.sha256(repr(screenshot).encode("utf-8", errors="replace")).hexdigest()
        payload = json.dumps(
            {
                "keys": sorted(observation),
                "screenshot_sha256": screenshot_digest,
                "instruction_present": bool(observation.get("instruction")),
                "accessibility_tree_present": observation.get("accessibility_tree") is not None,
                "terminal_present": observation.get("terminal") is not None,
            },
            sort_keys=True,
        ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@contextmanager
def working_directory(path: Path):
    """Temporarily use upstream as cwd for its relative configs/cache paths."""

    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def callable_path(function: Any) -> str:
    module = str(getattr(function, "__module__", "") or "")
    name = str(
        getattr(function, "__qualname__", "")
        or getattr(function, "__name__", "")
        or type(function).__qualname__
    )
    return f"{module}.{name}" if module else name


def _instrument_dispatch(
    value: Any,
    *,
    kind: str,
    trace: list[dict[str, Any]],
) -> tuple[Any, list[dict[str, Any]]]:
    """Wrap evaluator callables while preserving upstream call semantics."""

    is_list = isinstance(value, list)
    values = value if is_list else [value]
    wrapped: list[Any] = []
    bindings: list[dict[str, Any]] = []
    for index, function in enumerate(values):
        if function is None:
            wrapped.append(None)
            continue
        path = callable_path(function)
        bindings.append({"index": index, "path": path})

        @functools.wraps(function)
        def traced(*args: Any, __function: Any = function, __index: int = index, __path: str = path, **kwargs: Any):
            record = {
                "kind": kind,
                "index": __index,
                "path": __path,
                "entered": True,
                "completed": False,
            }
            trace.append(record)
            try:
                result = __function(*args, **kwargs)
            except Exception as exc:
                record["exception_type"] = type(exc).__name__
                raise
            record["completed"] = True
            return result

        wrapped.append(traced)
    return (wrapped if is_list else wrapped[0]), bindings


def execute_official_evaluator(environment: Any, *, infeasible: bool) -> dict[str, Any]:
    """Run and trace the real evaluator with an empty action history."""

    evaluator_config = getattr(environment, "evaluator", None)
    if not isinstance(evaluator_config, dict):
        raise TypeError("DesktopEnv evaluator configuration is unavailable")
    task_evaluator_sha256 = canonical_digest(evaluator_config)
    evaluator_func = evaluator_config.get("func")
    actual_infeasible = evaluator_func == "infeasible"
    if actual_infeasible is not infeasible:
        raise ValueError("source case infeasible flag disagrees with official evaluator func")

    expected_getter = getattr(environment, "expected_getter")
    evaluator_expected = evaluator_config.get("expected")
    if isinstance(expected_getter, list):
        expected_values = evaluator_expected if isinstance(evaluator_expected, list) else []
        expected_required_indices = [
            index
            for index, function in enumerate(expected_getter)
            if function is not None
            and index < len(expected_values)
            and bool(expected_values[index])
        ]
    else:
        expected_required_indices = (
            [0] if expected_getter is not None and bool(evaluator_expected) else []
        )

    trace: list[dict[str, Any]] = []
    bound_dispatch: dict[str, list[dict[str, Any]]] = {}
    for attribute, kind in (
        ("result_getter", "result_getter"),
        ("expected_getter", "expected_getter"),
        ("metric", "metric"),
    ):
        instrumented, bindings = _instrument_dispatch(
            getattr(environment, attribute), kind=kind, trace=trace
        )
        setattr(environment, attribute, instrumented)
        bound_dispatch[f"{kind}_bindings"] = bindings

    history_empty_before = len(environment.action_history) == 0
    if not history_empty_before:
        raise RuntimeError("official evaluator must start with an empty action history")
    raw_score = environment.evaluate()
    history_empty_after = len(environment.action_history) == 0
    if isinstance(raw_score, bool):
        raise TypeError("official evaluator returned bool instead of a numeric score")
    score = float(raw_score)
    score_finite = math.isfinite(score)
    completed = {
        (record["kind"], record["index"], record["path"])
        for record in trace
        if record.get("entered") is True and record.get("completed") is True
    }
    all_trace_records_completed = all(
        record.get("entered") is True
        and record.get("completed") is True
        and "exception_type" not in record
        for record in trace
    )
    result_bindings = {
        (binding["index"], binding["path"])
        for binding in bound_dispatch["result_getter_bindings"]
    }
    expected_bindings = {
        (binding["index"], binding["path"])
        for binding in bound_dispatch["expected_getter_bindings"]
    }
    metric_bindings = {
        (binding["index"], binding["path"])
        for binding in bound_dispatch["metric_bindings"]
    }
    completed_results = {
        (index, path) for kind, index, path in completed if kind == "result_getter"
    }
    completed_expected = {
        (index, path) for kind, index, path in completed if kind == "expected_getter"
    }
    completed_metrics = {
        (index, path) for kind, index, path in completed if kind == "metric"
    }
    executed_metric_indices = {index for index, _ in completed_metrics}
    result_indices = {index for index, _ in completed_results & result_bindings}
    expected_indices = {index for index, _ in completed_expected & expected_bindings}
    metric_getter_index_pairs_valid = all(
        index in result_indices
        and (index not in expected_required_indices or index in expected_indices)
        for index in executed_metric_indices
    )
    trace_paths_bound = all(
        (index, path) in {
            "result_getter": result_bindings,
            "expected_getter": expected_bindings,
            "metric": metric_bindings,
        }[kind]
        for kind, index, path in completed
    )
    result_getter_executed = bool(completed_results)
    expected_getter_executed = bool(completed_expected)
    gold_metric_executed = bool(completed_metrics)
    dispatch_trace_valid = all((
        all_trace_records_completed,
        trace_paths_bound,
        metric_getter_index_pairs_valid,
        not trace if infeasible else result_getter_executed and gold_metric_executed,
    ))
    return {
        "official_evaluator_executed": True,
        "infeasible": infeasible,
        "metric_applicability": (
            "not_applicable_infeasible" if infeasible else "case_specific_gold_metric"
        ),
        "action_history_empty_before": history_empty_before,
        "action_history_empty_after": history_empty_after,
        "score": score,
        "score_raw_type": type(raw_score).__name__,
        "score_numeric_finite": score_finite,
        "result_getter_executed": result_getter_executed,
        "expected_getter_executed": expected_getter_executed,
        "gold_metric_executed": gold_metric_executed,
        "evaluator_func": evaluator_func,
        "task_evaluator_sha256": task_evaluator_sha256,
        "expected_getter_required_indices": expected_required_indices,
        "all_trace_records_completed": all_trace_records_completed,
        "metric_getter_index_pairs_valid": metric_getter_index_pairs_valid,
        "dispatch_trace_valid": dispatch_trace_valid,
        "bound_dispatch": bound_dispatch,
        "execution_trace": trace,
    }


class SetupCallTracer:
    """Trace official SetupController.setup return values across reset phases."""

    def __init__(self, setup_controller_class: Any):
        self.setup_controller_class = setup_controller_class
        self.original_setup = setup_controller_class.setup
        self.phase = "unassigned"
        self.calls: list[dict[str, Any]] = []

    def install(self) -> None:
        tracer = self
        original_setup = self.original_setup

        @functools.wraps(original_setup)
        def traced(instance: Any, config: Any, *args: Any, **kwargs: Any):
            record = {
                "phase": tracer.phase,
                "config_count": len(config) if isinstance(config, list) else None,
                "config_sha256": canonical_digest(config),
                "entered": True,
                "completed": False,
            }
            tracer.calls.append(record)
            try:
                result = original_setup(instance, config, *args, **kwargs)
            except Exception as exc:
                record["exception_type"] = type(exc).__name__
                raise
            record["completed"] = True
            record["returned_true"] = result is True
            return result

        self.setup_controller_class.setup = traced

    def set_phase(self, phase: str) -> None:
        self.phase = phase

    def phase_result(self, phase: str) -> dict[str, Any]:
        calls = [record for record in self.calls if record.get("phase") == phase]
        return {
            "call_count": len(calls),
            "all_calls_completed": bool(calls) and all(
                record.get("completed") is True and "exception_type" not in record
                for record in calls
            ),
            "last_call_returned_true": bool(calls)
            and calls[-1].get("returned_true") is True,
        }

    def restore(self) -> None:
        self.setup_controller_class.setup = self.original_setup


def docker_container_id(environment: Any) -> str:
    provider = getattr(environment, "provider", None)
    container = getattr(provider, "container", None)
    return str(getattr(container, "id", "") or "")


def verify_docker_containers_absent(
    container_ids: list[str],
    *,
    client_factory: Any = None,
) -> dict[str, Any]:
    """Verify known provider containers are absent on docker.from_env's daemon."""

    unique_ids = sorted({value for value in container_ids if value})
    result: dict[str, Any] = {
        "attempted": bool(unique_ids),
        "known_container_ids": unique_ids,
        "absent_container_ids": [],
        "residual_container_ids": [],
        "passed": not unique_ids,
    }
    if not unique_ids:
        return result
    client = None
    try:
        if client_factory is None:
            import docker

            client = docker.from_env()
            not_found_error = docker.errors.NotFound
        else:
            client = client_factory()
            not_found_error = getattr(client, "not_found_error", LookupError)
        for container_id in unique_ids:
            try:
                client.containers.get(container_id)
            except not_found_error:
                result["absent_container_ids"].append(container_id)
            except Exception as exc:
                result["probe_error"] = type(exc).__name__
                result["residual_container_ids"].append(container_id)
            else:
                result["residual_container_ids"].append(container_id)
        result["passed"] = (
            not result["residual_container_ids"]
            and len(result["absent_container_ids"]) == len(unique_ids)
        )
    except Exception as exc:
        result["probe_error"] = type(exc).__name__
        result["passed"] = False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    return result


class _ProviderPathProxy:
    """Delegate every path operation except the provider's KVM device test."""

    def __init__(self, delegate: Any):
        self._delegate = delegate

    def exists(self, path: Any) -> bool:
        if os.fspath(path) == "/dev/kvm":
            return True
        return bool(self._delegate.exists(path))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _ProviderOSProxy:
    """Module-local proxy; assigning it never changes Python's global ``os``."""

    def __init__(self, delegate: Any):
        self._delegate = delegate
        self.path = _ProviderPathProxy(delegate.path)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def probe_docker_kvm_device(docker_image: str) -> dict[str, Any]:
    """Ask the Linux Docker daemon whether /dev/kvm can be passed through."""

    docker_cli = shutil.which("docker")
    command = [
        docker_cli or "docker", "run", "--rm", "--device", "/dev/kvm",
        "--entrypoint", "sh", docker_image, "-c", "test -c /dev/kvm",
    ]
    if docker_cli is None:
        return {
            "attempted": False,
            "device_available": False,
            "exit_code": None,
            "command": command[1:],
            "detail": "docker_cli_missing",
        }
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "attempted": True,
            "device_available": False,
            "exit_code": None,
            "command": command[1:],
            "detail": type(exc).__name__,
        }
    detail = (result.stderr or result.stdout or "").strip()[-300:]
    return {
        "attempted": True,
        "device_available": result.returncode == 0,
        "exit_code": result.returncode,
        "command": command[1:],
        "detail": detail,
    }


def install_docker_kvm_provider_adapter(provider_module: Any, *, enabled: bool) -> tuple[Any, dict[str, Any]]:
    """Install a reversible proxy only in the pinned Docker provider module."""

    original_os = provider_module.os
    if enabled:
        provider_module.os = _ProviderOSProxy(original_os)
    evidence = {
        "scope": "desktop_env.providers.docker.provider.os",
        "enabled": enabled,
        "kvm_exists_overridden": enabled,
        "provider_module_os_replaced": enabled,
        "global_os_patched": False,
        "upstream_source_modified": False,
        "acceleration_mode": "kvm" if enabled else "tcg",
    }
    return original_os, evidence


def install_docker_port_allocation_race_adapter(
    provider_module: Any,
) -> tuple[Any, dict[str, Any]]:
    """Ignore containers removed concurrently while the provider scans ports."""

    provider_class = provider_module.DockerProvider
    original = provider_class._get_used_ports
    state = {
        "enabled": True,
        "containers_list_ignore_removed": True,
        "not_found_skipped": 0,
        "upstream_source_modified": False,
    }

    def resilient_get_used_ports(instance: Any):
        system_ports = {
            connection.laddr.port
            for connection in provider_module.psutil.net_connections()
        }
        docker_ports: set[int] = set()
        containers = instance.client.containers.list(ignore_removed=True)
        for container in containers:
            try:
                attrs = container.attrs
            except provider_module.docker.errors.NotFound:
                state["not_found_skipped"] += 1
                continue
            network = attrs.get("NetworkSettings") if isinstance(attrs, dict) else {}
            ports = network.get("Ports") if isinstance(network, dict) else {}
            if not isinstance(ports, dict):
                continue
            for port_mappings in ports.values():
                if not isinstance(port_mappings, list):
                    continue
                for mapping in port_mappings:
                    if isinstance(mapping, dict) and str(mapping.get("HostPort", "")).isdigit():
                        docker_ports.add(int(mapping["HostPort"]))
        return system_ports | docker_ports

    provider_class._get_used_ports = resilient_get_used_ports
    return original, state


def emit(report: dict[str, Any], output: str | None) -> None:
    if output:
        write_json(Path(output).resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def _main_unlocked() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source-native-root", default="artifacts/source-native-v4")
    parser.add_argument("--upstream-root", default="upstream/osworld")
    parser.add_argument("--provider", default="docker")
    parser.add_argument("--path-to-vm", default=DEFAULT_OSWORLD_VM_PATH)
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
    parser.add_argument("--docker-image", default="happysixd/osworld-docker")
    parser.add_argument("--snapshot-name", default="init_state")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--provider-lock-timeout-seconds", type=float, default=600.0)
    args = parser.parse_args()

    upstream_root = (ROOT / args.upstream_root).resolve()
    cases = load_osworld_cases(
        ROOT,
        source_native_root=(ROOT / args.source_native_root).resolve(),
        upstream_root=upstream_root,
    )
    case = next((item for item in cases if item.case_id == args.case_id), None)
    if case is None:
        raise SystemExit(f"unknown OSWorld case: {args.case_id}")
    official_task_template = copy.deepcopy(case.task)
    official_task_pre_execution_sha256 = canonical_digest(official_task_template)
    official_evaluator_template = official_task_template.get("evaluator")
    if not isinstance(official_evaluator_template, dict):
        raise TypeError("official OSWorld task evaluator configuration is unavailable")
    official_task_evaluator_pre_execution_sha256 = canonical_digest(
        official_evaluator_template
    )

    path_to_vm = Path(args.path_to_vm)
    if not path_to_vm.is_absolute():
        path_to_vm = ROOT / path_to_vm
    path_to_vm = path_to_vm.resolve()
    asset_attestation = Path(args.asset_attestation)
    if not asset_attestation.is_absolute():
        asset_attestation = ROOT / asset_attestation
    asset_attestation = asset_attestation.resolve()
    bootstrap_report = Path(args.bootstrap_report)
    if not bootstrap_report.is_absolute():
        bootstrap_report = ROOT / bootstrap_report
    bootstrap_report = bootstrap_report.resolve()
    environment_lock = Path(args.environment_lock)
    if not environment_lock.is_absolute():
        environment_lock = ROOT / environment_lock
    environment_lock = environment_lock.resolve()
    if args.preflight_only and not path_to_vm.is_file():
        report = {
            "schema_version": "osworld-native-environment-v2",
            "case_id": case.case_id,
            "benchmark": "OSWorld",
            "source_task_id": case.source_task_id,
            "execution_scope": "native_environment_smoke",
            "status": "blocked_real_vm_prerequisites",
            "provider_preflight": {
                "provider": args.provider,
                "configuration_resolved": False,
                "launch_ready": False,
                "launch_attempted": False,
                "launch_succeeded": False,
                "blockers": ["osworld_vm_disk_missing"],
                "details": {
                    "vm_disk_path": str(path_to_vm),
                    "vm_disk_present": False,
                    "fast_fail_before_live_provider_probe": True,
                },
            },
            "fallback_used": False,
            "real_vm_executed": False,
            "model_episode_executed": False,
            "official_task_setup_executed": False,
            "official_gold_metric_executed": False,
            "official_evaluator_executed": False,
        }
        emit(report, args.output)
        return 2
    provider_probe = probe_real_vm_provider(
        upstream_root,
        provider=args.provider,
        path_to_vm=path_to_vm,
        docker_image=args.docker_image,
        asset_attestation=asset_attestation,
        bootstrap_report=bootstrap_report,
        environment_lock=environment_lock,
    )
    report: dict[str, Any] = {
        "schema_version": "osworld-native-environment-v2",
        "case_id": case.case_id,
        "benchmark": "OSWorld",
        "source_task_id": case.source_task_id,
        "execution_scope": "native_environment_smoke",
        "status": "preflight_ready" if provider_probe.launch_ready else "blocked_real_vm_prerequisites",
        "provider_preflight": provider_probe.as_dict(),
        "fallback_used": False,
        "real_vm_executed": False,
        "model_episode_executed": False,
        "official_task_setup_executed": False,
        "official_gold_metric_executed": False,
        "official_evaluator_executed": False,
    }
    if args.preflight_only or not provider_probe.launch_ready:
        emit(report, args.output)
        return 0 if provider_probe.launch_ready else 2

    # launch_ready implies an already-present disk.  Never let the upstream
    # manager's implicit multi-GB download path run from this entry point.
    if path_to_vm is None or not path_to_vm.is_file():
        report["status"] = "blocked_explicit_vm_path_required"
        report["provider_preflight"]["blockers"].append("explicit_vm_path_required_for_launch")
        emit(report, args.output)
        return 2
    if args.provider == "docker" and args.docker_image != "happysixd/osworld-docker":
        report["status"] = "blocked_unsupported_image_override"
        report["provider_preflight"]["blockers"].append("upstream_docker_provider_uses_hardcoded_image")
        emit(report, args.output)
        return 2
    if args.provider != "docker":
        report["status"] = "blocked_native_profile_requires_docker"
        report["provider_preflight"]["blockers"].append(
            "native_v2_requires_docker_container_replacement_evidence"
        )
        emit(report, args.output)
        return 2

    environment = None
    docker_provider_module = None
    original_provider_os = None
    original_get_used_ports = None
    setup_tracer = None
    known_provider_container_ids: list[str] = []
    report["provider_preflight"]["launch_attempted"] = True
    try:
        with working_directory(upstream_root):
            if str(upstream_root) not in sys.path:
                sys.path.insert(0, str(upstream_root))
            from desktop_env.controllers.setup import SetupController
            from desktop_env.desktop_env import DesktopEnv
            from desktop_env.providers.docker import provider as docker_provider_module

            kvm_probe = probe_docker_kvm_device(args.docker_image)
            original_provider_os, compatibility_adapter = install_docker_kvm_provider_adapter(
                docker_provider_module,
                enabled=kvm_probe["device_available"] is True,
            )
            original_get_used_ports, port_allocation_adapter = (
                install_docker_port_allocation_race_adapter(docker_provider_module)
            )
            compatibility_adapter["port_allocation_race_adapter"] = (
                port_allocation_adapter
            )
            report["kvm_probe"] = kvm_probe
            report["runtime_compatibility_adapter"] = compatibility_adapter

            environment = DesktopEnv(
                provider_name=args.provider,
                path_to_vm=str(path_to_vm),
                snapshot_name=args.snapshot_name,
                action_space="pyautogui",
                headless=args.headless,
                os_type="Ubuntu",
                require_a11y_tree=False,
                require_terminal=False,
            )
            known_provider_container_ids.append(docker_container_id(environment))
            report["provider_preflight"]["launch_succeeded"] = True
            setup_tracer = SetupCallTracer(SetupController)
            setup_tracer.install()
            lifecycle_phase_order: list[str] = []

            setup_tracer.set_phase("first_reset_task_setup")
            first_observation = environment.reset(copy.deepcopy(official_task_template))
            lifecycle_phase_order.append("first_reset")
            first_digest = observation_digest(first_observation)
            first_container = docker_container_id(environment)
            known_provider_container_ids.append(first_container)

            setup_tracer.set_phase("official_evaluator_postconfig")
            evaluator_probe = execute_official_evaluator(
                environment, infeasible=case.is_infeasible
            )
            lifecycle_phase_order.append("official_evaluator")

            action_history_before_wait = list(environment.action_history)
            _, wait_reward, wait_done, wait_info = environment.step("WAIT", pause=0)
            action_history_after_wait = list(environment.action_history)
            used_after_wait = environment.is_environment_used is True
            lifecycle_phase_order.append("wait")

            setup_tracer.set_phase("second_reset_task_setup")
            second_observation = environment.reset(copy.deepcopy(official_task_template))
            lifecycle_phase_order.append("second_reset")
            second_digest = observation_digest(second_observation)
            second_container = docker_container_id(environment)
            known_provider_container_ids.append(second_container)
            history_cleared = len(environment.action_history) == 0
            setup_probe = {
                "calls": setup_tracer.calls,
                "phase_results": {
                    phase: setup_tracer.phase_result(phase)
                    for phase in (
                        "first_reset_task_setup",
                        "official_evaluator_postconfig",
                        "second_reset_task_setup",
                    )
                },
            }

        docker_replaced = (
            len(first_container) == 64
            and len(second_container) == 64
            and first_container != second_container
        )
        first_setup_valid = all((
            setup_probe["phase_results"]["first_reset_task_setup"]["all_calls_completed"],
            setup_probe["phase_results"]["first_reset_task_setup"]["last_call_returned_true"],
        ))
        evaluator_setup_valid = all((
            setup_probe["phase_results"]["official_evaluator_postconfig"]["all_calls_completed"],
            setup_probe["phase_results"]["official_evaluator_postconfig"]["last_call_returned_true"],
        ))
        second_setup_valid = all((
            setup_probe["phase_results"]["second_reset_task_setup"]["all_calls_completed"],
            setup_probe["phase_results"]["second_reset_task_setup"]["last_call_returned_true"],
        ))
        case_task_spec_immutable = (
            canonical_digest(case.task) == official_task_pre_execution_sha256
        )
        evaluator_valid = all((
            evaluator_probe["official_evaluator_executed"] is True,
            evaluator_probe["action_history_empty_before"] is True,
            evaluator_probe["action_history_empty_after"] is True,
            evaluator_probe["score_numeric_finite"] is True,
            evaluator_probe["dispatch_trace_valid"] is True,
            evaluator_probe["task_evaluator_sha256"]
            == official_task_evaluator_pre_execution_sha256,
            case_task_spec_immutable,
            (
                evaluator_probe["metric_applicability"] == "not_applicable_infeasible"
                and evaluator_probe["evaluator_func"] == "infeasible"
                and evaluator_probe["score"] == 0.0
                and evaluator_probe["gold_metric_executed"] is False
                and evaluator_probe["result_getter_executed"] is False
            )
            if case.is_infeasible
            else (
                evaluator_probe["metric_applicability"] == "case_specific_gold_metric"
                and evaluator_probe["evaluator_func"] != "infeasible"
                and evaluator_probe["gold_metric_executed"] is True
                and evaluator_probe["result_getter_executed"] is True
            ),
        ))
        wait_reward_numeric = (
            not isinstance(wait_reward, bool)
            and math.isfinite(float(wait_reward))
            and float(wait_reward) == 0.0
        )
        wait_valid = all((
            action_history_before_wait == [],
            action_history_after_wait == ["WAIT"],
            wait_reward_numeric,
            wait_done is False,
            wait_info == {},
            used_after_wait,
            lifecycle_phase_order == [
                "first_reset", "official_evaluator", "wait", "second_reset",
            ],
        ))
        official_task_setup_valid = first_setup_valid and second_setup_valid
        checks = {
            "real_environment_imported": True,
            "real_environment_started": True,
            "official_task_setup_executed": official_task_setup_valid,
            "first_reset_task_setup_succeeded": first_setup_valid,
            "evaluator_postconfig_setup_succeeded": evaluator_setup_valid,
            "second_reset_task_setup_succeeded": second_setup_valid,
            "official_evaluator_executed": evaluator_valid,
            "evaluator_score_numeric_finite": evaluator_probe["score_numeric_finite"],
            "case_specific_result_getter_executed": evaluator_probe["result_getter_executed"],
            "case_specific_gold_metric_executed": evaluator_probe["gold_metric_executed"],
            "wait_marked_environment_used": wait_valid,
            "second_reset_completed": True,
            "docker_container_replaced": docker_replaced,
            "action_history_cleared_on_second_reset": history_cleared,
            "docker_kvm_probe_completed": kvm_probe["attempted"] is True,
            "provider_module_adapter_consistent": (
                compatibility_adapter["enabled"] is kvm_probe["device_available"]
            ),
            "case_task_spec_immutable": case_task_spec_immutable,
        }
        report.update({
            "execution_scope": "native_runtime",
            "qualification_profile": "osworld_native_environment_v2",
            "real_vm_executed": True,
            "official_task_setup_executed": official_task_setup_valid,
            "official_evaluator_executed": evaluator_valid,
            "official_gold_metric_executed": evaluator_probe["gold_metric_executed"],
            "model_episode_executed": False,
            "official_task_config_sha256": case.config_sha256,
            "official_evaluator_source_sha256": case.dispatch.evaluator_sha256,
            "official_task_pre_execution_sha256": official_task_pre_execution_sha256,
            "official_task_evaluator_pre_execution_sha256": (
                official_task_evaluator_pre_execution_sha256
            ),
            "checks": checks,
            "setup_probe": setup_probe,
            "evaluator_probe": evaluator_probe,
            "wait_probe": {
                "action": "WAIT",
                "reward": float(wait_reward),
                "done": bool(wait_done),
                "info": wait_info,
                "environment_used_after_wait": used_after_wait,
                "action_history_before": action_history_before_wait,
                "action_history_after": action_history_after_wait,
            },
            "reset_probe": {
                "provider": args.provider,
                "first_observation_sha256": first_digest,
                "second_observation_sha256": second_digest,
                "observation_equality_required": False,
                "first_container_id": first_container,
                "second_container_id": second_container,
                "container_replaced": docker_replaced,
                "action_history_cleared": history_cleared,
                "second_reset_completed": True,
                "lifecycle_phase_order": lifecycle_phase_order,
            },
        })
        required_checks = (
            "real_environment_imported",
            "real_environment_started",
            "official_task_setup_executed",
            "first_reset_task_setup_succeeded",
            "evaluator_postconfig_setup_succeeded",
            "second_reset_task_setup_succeeded",
            "official_evaluator_executed",
            "evaluator_score_numeric_finite",
            "wait_marked_environment_used",
            "second_reset_completed",
            "docker_container_replaced",
            "action_history_cleared_on_second_reset",
            "docker_kvm_probe_completed",
            "provider_module_adapter_consistent",
            "case_task_spec_immutable",
        )
        report["status"] = (
            "native_environment_validated"
            if all(checks[name] is True for name in required_checks)
            else "native_environment_validation_failed"
        )
    except Exception as exc:
        report.update({
            "status": "native_environment_validation_failed",
            "failure": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=20)[-8000:],
            },
        })
    finally:
        if environment is not None:
            known_provider_container_ids.append(docker_container_id(environment))
            try:
                with working_directory(upstream_root):
                    environment.close()
            except Exception as exc:
                report["close_failure"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=20)[-8000:],
                }
                report["status"] = "native_environment_validation_failed"
        if setup_tracer is not None:
            setup_tracer.restore()
        if docker_provider_module is not None and original_provider_os is not None:
            docker_provider_module.os = original_provider_os
        if docker_provider_module is not None and original_get_used_ports is not None:
            docker_provider_module.DockerProvider._get_used_ports = original_get_used_ports

    cleanup_verification = verify_docker_containers_absent(
        known_provider_container_ids
    )
    report["provider_cleanup_verification"] = cleanup_verification
    if cleanup_verification["attempted"] and not cleanup_verification["passed"]:
        report["status"] = "native_environment_validation_failed"

    if report["status"] == "native_environment_validated":
        report["evidence_sha256"] = canonical_digest(report)
    emit(report, args.output)
    return 0 if report["status"] == "native_environment_validated" else 1


def main() -> int:
    configure_utf8_process_stdio()
    lock_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    lock_parser.add_argument("--path-to-vm", default=DEFAULT_OSWORLD_VM_PATH)
    lock_parser.add_argument("--preflight-only", action="store_true")
    lock_parser.add_argument(
        "--provider-lock-timeout-seconds",
        type=float,
        default=600.0,
    )
    lock_args, _ = lock_parser.parse_known_args()
    vm_path = Path(lock_args.path_to_vm)
    if not vm_path.is_absolute():
        vm_path = ROOT / vm_path
    vm_path = vm_path.resolve()
    if lock_args.preflight_only and not vm_path.is_file():
        return _main_unlocked()
    lock_path = osworld_provider_lock_path(vm_path)
    lock = FileLock(str(lock_path))
    try:
        lock.acquire(timeout=max(0.0, lock_args.provider_lock_timeout_seconds))
    except Timeout:
        report = {
            "schema_version": "osworld-native-environment-v2",
            "status": "blocked_provider_vm_lock_held",
            "provider_lock_path": str(lock_path),
            "vm_disk_path": str(vm_path),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    try:
        return _main_unlocked()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
