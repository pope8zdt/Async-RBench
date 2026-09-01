import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from filelock import FileLock

import scripts.run_osworld_native_batch as batch
import scripts.run_osworld_native_case as direct
from async_rbench.osworld_runtime import osworld_provider_lock_path
from scripts.run_osworld_native_case import (
    configure_utf8_process_stdio,
    install_docker_port_allocation_race_adapter,
    utf8_subprocess_environment,
    verify_docker_containers_absent,
)


def _identity():
    return {
        "id": "daemon-1",
        "name": "desktop-linux",
        "server_version": "27.0",
        "docker_root_dir": "/var/lib/docker",
        "os_type": "linux",
        "architecture": "x86_64",
    }


def _runtime_probes(*, context="desktop-linux"):
    identity = _identity()
    images = {"untagged": "image", "digest": "image", "latest": "image"}
    return {
        "lock_path": "provider.lock",
        "lock_acquired": True,
        "kvm_probe": {"attempted": True, "device_available": False, "exit_code": 1},
        "docker_cli_daemon": {
            "probe_succeeded": True,
            "context": context,
            "daemon_identity": dict(identity),
        },
        "docker_sdk_provider": {
            "probe_succeeded": True,
            "client_base_url": "npipe://desktop",
            "daemon_identity": dict(identity),
            "image_identities": images,
        },
        "container_probe": {
            "probe_succeeded": True,
            "official_container_ids": [],
            "provider_container_ids": [],
        },
    }


def _provider_probe():
    details = {
        "daemon_reachable": True,
        "docker_image_present": True,
        "docker_digest_image_present": True,
        "docker_latest_image_present": True,
        "vm_disk_present": True,
        "asset_attestation_verified": True,
        "python_bootstrap_verified": True,
        "factory_sha256": "a" * 64,
        "provider_source_sha256": "b" * 64,
        "manager_source_sha256": "c" * 64,
    }
    return SimpleNamespace(
        provider="docker",
        configuration_resolved=True,
        launch_ready=True,
        blockers=(),
        details=details,
        as_dict=lambda: {
            "provider": "docker",
            "configuration_resolved": True,
            "launch_ready": True,
            "blockers": [],
            "details": dict(details),
        },
    )


def _case():
    return SimpleNamespace(
        case_id="case-1",
        source_task_id="source-1",
        upstream_revision="d" * 40,
        config_sha256="e" * 64,
        dispatch=SimpleNamespace(evaluator_sha256="f" * 64),
        task={"config": [], "evaluator": {"func": "metric"}},
    )


def _prepare_main(monkeypatch, tmp_path, *, runtime_probe_fn=None):
    case = _case()
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"qcow")
    attestation = tmp_path / "asset_attestation.json"
    attestation.write_text("{}\n", encoding="utf-8")
    bootstrap = tmp_path / "bootstrap.json"
    bootstrap.write_text("{}\n", encoding="utf-8")
    lock = tmp_path / "requirements.lock"
    lock.write_text("package==1\n", encoding="utf-8")
    output = tmp_path / "output"
    monkeypatch.setattr(batch, "load_osworld_cases", lambda *args, **kwargs: [case])
    monkeypatch.setattr(
        batch,
        "validate_osworld_python_bootstrap",
        lambda *args, **kwargs: (
            True,
            [],
            {
                "python_environment_isolated": True,
                "python_bootstrap_report_sha256": "1" * 64,
                "python_environment_lock_sha256": "2" * 64,
            },
        ),
    )
    monkeypatch.setattr(batch, "probe_real_vm_provider", lambda *args, **kwargs: _provider_probe())
    monkeypatch.setattr(
        batch,
        "probe_upstream_git_binding",
        lambda _root: {
            "probe_succeeded": True,
            "tracked_tree_clean": True,
            "revision": case.upstream_revision,
        },
    )
    monkeypatch.setattr(
        batch,
        "run_locked_provider_runtime_probes",
        runtime_probe_fn or (lambda *args, **kwargs: _runtime_probes()),
    )
    monkeypatch.setattr(
        batch,
        "inspect_provider_containers_under_lock",
        lambda *args, **kwargs: {
            "lock_acquired": True,
            "probe_succeeded": True,
            "official_container_ids": [],
            "provider_container_ids": [],
        },
    )
    argv = [
        "run_osworld_native_batch.py",
        "--case-id", case.case_id,
        "--path-to-vm", str(vm),
        "--asset-attestation", str(attestation),
        "--bootstrap-report", str(bootstrap),
        "--environment-lock", str(lock),
        "--output", str(output),
        "--retry-backoff-seconds", "0",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    return case, output


def test_batch_main_resume_passes_current_source_binding_to_matcher(monkeypatch, tmp_path):
    case, output = _prepare_main(monkeypatch, tmp_path)
    evidence = output / "cases" / f"{case.case_id}.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"status":"native_environment_validated"}\n', encoding="utf-8")
    received = {}

    def reusable(_entry, _case, **kwargs):
        received.update(kwargs)
        return True

    monkeypatch.setattr(batch, "reusable_evidence", reusable)
    assert batch._main_unlocked() == 0
    assert received["upstream_git_binding"]["revision"] == case.upstream_revision
    assert received["current_provider_details"]["factory_sha256"] == "a" * 64
    report = json.loads((output / "batch_report.json").read_text(encoding="utf-8"))
    assert report["results"][0]["skipped_already_valid"] is True
    assert report["atomic_sync_required"] is False
    assert report["sync_command"] is None


def test_batch_main_retries_process_error_then_fresh_accepts_with_current_binding(
    monkeypatch, tmp_path
):
    case, output = _prepare_main(monkeypatch, tmp_path)
    calls = {"count": 0, "environments": []}
    received = {}

    def run(command, **kwargs):
        calls["count"] += 1
        calls["environments"].append(kwargs["env"])
        if calls["count"] == 1:
            raise OSError("transient spawn failure")
        evidence_path = Path(command[command.index("--output") + 1])
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps({
                "status": "native_environment_validated",
                "provider_cleanup_verification": {"passed": True},
            }) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    def matches(_entry, _case, **kwargs):
        received.update(kwargs)
        return True

    monkeypatch.setattr(batch.subprocess, "run", run)
    monkeypatch.setattr(batch, "qualify_entry_safely", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(batch, "evidence_matches_current_case", matches)
    assert batch._main_unlocked() == 0
    assert calls["count"] == 2
    assert all(
        environment["PYTHONUTF8"] == "1"
        and environment["PYTHONIOENCODING"] == "utf-8:backslashreplace"
        for environment in calls["environments"]
    )
    assert received["upstream_git_binding"]["revision"] == case.upstream_revision
    report = json.loads((output / "batch_report.json").read_text(encoding="utf-8"))
    result = report["results"][0]
    assert result["qualified"] is True
    assert result["attempt_count"] == 2
    assert result["attempts"][0]["process_failure"] == (
        "native_case_process_exception:OSError"
    )
    assert result["attempts"][1]["stdout_tail"] == "ok"


def test_direct_launcher_utf8_helpers_override_gbk_without_mutating_base_environment():
    base = {
        "KEEP": "yes",
        "PYTHONUTF8": "0",
        "PYTHONIOENCODING": "gbk",
    }
    child = utf8_subprocess_environment(base)
    assert base["PYTHONIOENCODING"] == "gbk"
    assert child == {
        "KEEP": "yes",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8:backslashreplace",
    }

    class Stream:
        def __init__(self):
            self.calls = []

        def reconfigure(self, **kwargs):
            self.calls.append(kwargs)

    environment = {"PYTHONIOENCODING": "gbk"}
    stdout = Stream()
    stderr = Stream()
    result = configure_utf8_process_stdio(
        environment=environment,
        stdout=stdout,
        stderr=stderr,
    )
    assert environment == {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8:backslashreplace",
    }
    assert stdout.calls == [{"encoding": "utf-8", "errors": "backslashreplace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "backslashreplace"}]
    assert result["streams_reconfigured"] == {"stdout": True, "stderr": True}


def test_direct_report_uses_frozen_official_evaluator_digest_and_preserves_case_spec(
    tmp_path, monkeypatch
):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"qcow")
    output = tmp_path / "case.json"
    task = {
        "config": [{"type": "task-setup"}],
        "evaluator": {
            "func": "fake_metric",
            "result": {"type": "official"},
            "expected": {"type": "official"},
            "postconfig": [{"type": "evaluator-setup"}],
        },
    }
    case = SimpleNamespace(
        case_id="case-mutating-evaluator",
        source_task_id="source-mutating-evaluator",
        task=task,
        is_infeasible=False,
        config_sha256="a" * 64,
        dispatch=SimpleNamespace(evaluator_sha256="b" * 64),
    )
    original_task_digest = direct.canonical_digest(case.task)
    original_evaluator_digest = direct.canonical_digest(case.task["evaluator"])

    class SetupController:
        def setup(self, _config, use_proxy=False):
            return True

    reset_tasks = []

    class DesktopEnv:
        def __init__(self, **_kwargs):
            self.action_history = []
            self.is_environment_used = False
            self.provider = SimpleNamespace(
                container=SimpleNamespace(id="0" * 64)
            )
            self.reset_count = 0

        def reset(self, reset_task):
            reset_tasks.append(reset_task)
            self.reset_count += 1
            self.action_history = []
            self.is_environment_used = False
            self.evaluator = reset_task["evaluator"]
            self.result_getter = lambda environment, config: config["value"]
            self.expected_getter = lambda environment, config: config["value"]
            self.metric = lambda actual, expected: float(actual == expected)
            SetupController().setup(reset_task["config"])
            self.provider.container = SimpleNamespace(
                id=str(self.reset_count) * 64
            )
            return {"screenshot": b"image"}

        def evaluate(self):
            SetupController().setup(self.evaluator["postconfig"])
            actual = self.result_getter(self, {"value": "same"})
            expected = self.expected_getter(self, {"value": "same"})
            self.evaluator["result"]["type"] = "runtime-mutated"
            self.evaluator["runtime_cache"] = {"created": True}
            return self.metric(actual, expected)

        def step(self, action, pause=0):
            assert action == "WAIT" and pause == 0
            self.action_history.append(action)
            self.is_environment_used = True
            return None, 0.0, False, {}

        def close(self):
            return None

    setup_module = ModuleType("desktop_env.controllers.setup")
    setup_module.SetupController = SetupController
    controllers_module = ModuleType("desktop_env.controllers")
    controllers_module.setup = setup_module
    desktop_module = ModuleType("desktop_env.desktop_env")
    desktop_module.DesktopEnv = DesktopEnv
    provider_module = ModuleType("desktop_env.providers.docker.provider")

    class DockerProvider:
        def _get_used_ports(self):
            return set()

    provider_module.DockerProvider = DockerProvider
    provider_module.os = direct.os
    docker_module = ModuleType("desktop_env.providers.docker")
    docker_module.provider = provider_module
    providers_module = ModuleType("desktop_env.providers")
    providers_module.docker = docker_module
    desktop_package = ModuleType("desktop_env")
    desktop_package.controllers = controllers_module
    desktop_package.providers = providers_module
    monkeypatch.setitem(sys.modules, "desktop_env", desktop_package)
    monkeypatch.setitem(sys.modules, "desktop_env.controllers", controllers_module)
    monkeypatch.setitem(sys.modules, "desktop_env.controllers.setup", setup_module)
    monkeypatch.setitem(sys.modules, "desktop_env.desktop_env", desktop_module)
    monkeypatch.setitem(sys.modules, "desktop_env.providers", providers_module)
    monkeypatch.setitem(sys.modules, "desktop_env.providers.docker", docker_module)
    monkeypatch.setitem(
        sys.modules, "desktop_env.providers.docker.provider", provider_module
    )

    provider_probe = SimpleNamespace(
        launch_ready=True,
        as_dict=lambda: {
            "provider": "docker",
            "configuration_resolved": True,
            "launch_ready": True,
            "launch_attempted": False,
            "launch_succeeded": False,
            "blockers": [],
            "details": {},
        },
    )
    monkeypatch.setattr(direct, "load_osworld_cases", lambda *args, **kwargs: [case])
    monkeypatch.setattr(
        direct, "probe_real_vm_provider", lambda *args, **kwargs: provider_probe
    )
    monkeypatch.setattr(
        direct,
        "probe_docker_kvm_device",
        lambda _image: {
            "attempted": True,
            "device_available": False,
            "exit_code": 1,
            "command": [],
            "detail": "",
        },
    )
    monkeypatch.setattr(
        direct,
        "install_docker_port_allocation_race_adapter",
        lambda module: (
            module.DockerProvider._get_used_ports,
            {
                "enabled": True,
                "containers_list_ignore_removed": True,
                "not_found_skipped": 0,
                "upstream_source_modified": False,
            },
        ),
    )
    monkeypatch.setattr(
        direct,
        "verify_docker_containers_absent",
        lambda _ids: {
            "attempted": True,
            "known_container_ids": [],
            "absent_container_ids": [],
            "residual_container_ids": [],
            "passed": True,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_osworld_native_case.py",
            "--case-id", case.case_id,
            "--upstream-root", str(upstream),
            "--path-to-vm", str(vm),
            "--output", str(output),
        ],
    )

    assert direct._main_unlocked() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "native_environment_validated"
    assert report["checks"]["official_evaluator_executed"] is True
    assert report["checks"]["case_task_spec_immutable"] is True
    assert report["official_evaluator_executed"] is True
    assert report["evaluator_probe"]["task_evaluator_sha256"] == (
        original_evaluator_digest
    )
    assert report["official_task_evaluator_pre_execution_sha256"] == (
        original_evaluator_digest
    )
    assert direct.canonical_digest(case.task) == original_task_digest
    assert "runtime_cache" not in case.task["evaluator"]
    assert len(reset_tasks) == 2
    assert reset_tasks[0] is not reset_tasks[1]
    assert reset_tasks[0]["evaluator"]["result"]["type"] == "runtime-mutated"
    assert reset_tasks[1]["evaluator"]["result"]["type"] == "official"


def test_batch_postflight_context_switch_never_authorizes_sync(monkeypatch, tmp_path):
    probes = iter([_runtime_probes(), _runtime_probes(context="default")])
    case, output = _prepare_main(
        monkeypatch,
        tmp_path,
        runtime_probe_fn=lambda *args, **kwargs: next(probes),
    )
    evidence = output / "cases" / f"{case.case_id}.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"status":"native_environment_validated"}\n', encoding="utf-8")
    monkeypatch.setattr(batch, "reusable_evidence", lambda *args, **kwargs: True)
    assert batch._main_unlocked() == 1
    report = json.loads((output / "batch_report.json").read_text(encoding="utf-8"))
    assert report["live_provider_postflight"][
        "preflight_postflight_identity_stable"
    ] is False
    assert report["status"] == "native_collection_incomplete"
    assert report["atomic_sync_required"] is False
    assert report["sync_command"] is None


def test_direct_provider_vm_lock_rejects_a_second_process_without_live_probe(tmp_path):
    root = Path(__file__).resolve().parents[1]
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"qcow")
    lock = FileLock(str(osworld_provider_lock_path(vm)))
    with lock.acquire(timeout=0):
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "run_osworld_native_case.py"),
                "--case-id", "never-loaded",
                "--path-to-vm", str(vm),
                "--provider-lock-timeout-seconds", "0",
            ],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["status"] == "blocked_provider_vm_lock_held"


def test_batch_output_lock_rejects_a_second_writer_before_any_live_probe(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "shared-output"
    output.mkdir()
    lock = FileLock(str(output / ".osworld-native-batch.lock"))
    with lock.acquire(timeout=0):
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "run_osworld_native_batch.py"),
                "--case-id", "never-loaded",
                "--output", str(output),
                "--output-lock-timeout-seconds", "0",
            ],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    assert completed.returncode == 2
    report = json.loads(completed.stdout)
    assert report["status"] == "blocked_output_lock_held"
    assert report["output_path"] == str(output.resolve())


def test_container_inspection_skips_only_explicit_disappearance_and_keeps_osworld_residual(
    tmp_path,
):
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"qcow")
    gone_id = "1" * 64
    osworld_id = "2" * 64
    list_calls = {"count": 0}

    def run(command, **_kwargs):
        if command[1:3] == ["context", "show"]:
            return SimpleNamespace(returncode=0, stdout="desktop-linux\n", stderr="")
        if command[2:6] == ["ls", "--all", "--quiet", "--no-trunc"]:
            list_calls["count"] += 1
            ids = (
                f"{gone_id}\n{osworld_id}\n"
                if list_calls["count"] == 1
                else f"{osworld_id}\n"
            )
            return SimpleNamespace(
                returncode=0, stdout=ids, stderr=""
            )
        assert command[2] == "inspect"
        container_id = command[3]
        if container_id == gone_id:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr=f"Error response from daemon: No such container: {gone_id}",
            )
        record = [{
            "Id": osworld_id,
            "Image": batch.OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
            "Name": "/desktop-container",
            "State": {"Running": True, "Status": "running"},
            "Mounts": [{
                "Type": "bind",
                "Source": str(vm.resolve()),
                "Destination": "/System.qcow2",
                "RW": True,
            }],
        }]
        return SimpleNamespace(returncode=0, stdout=json.dumps(record), stderr="")

    result = batch.inspect_osworld_provider_containers(
        vm, docker_cli="docker", command_runner=run
    )
    assert result["probe_succeeded"] is True
    assert result["docker_context"] == "desktop-linux"
    assert result["containers_disappeared_during_inspect"] == [gone_id]
    assert result["official_container_ids"] == [osworld_id]
    assert result["provider_container_ids"] == [osworld_id]


def test_container_inspection_fails_closed_for_non_disappearance_inspect_error(tmp_path):
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"qcow")

    def run(command, **_kwargs):
        if command[1:3] == ["context", "show"]:
            return SimpleNamespace(returncode=0, stdout="desktop-linux\n", stderr="")
        if command[2:6] == ["ls", "--all", "--quiet", "--no-trunc"]:
            return SimpleNamespace(returncode=0, stdout=f"{'3' * 64}\n", stderr="")
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="permission denied while inspecting container",
        )

    result = batch.inspect_osworld_provider_containers(
        vm, docker_cli="docker", command_runner=run
    )
    assert result["probe_succeeded"] is False
    assert result["containers_disappeared_during_inspect"] == []
    assert result["error"] == "permission denied while inspecting container"


def test_container_disappearance_claim_is_rejected_when_full_id_still_exists(tmp_path):
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"qcow")
    container_id = "4" * 64

    def run(command, **_kwargs):
        if command[1:3] == ["context", "show"]:
            return SimpleNamespace(returncode=0, stdout="desktop-linux\n", stderr="")
        if command[2:6] == ["ls", "--all", "--quiet", "--no-trunc"]:
            return SimpleNamespace(returncode=0, stdout=f"{container_id}\n", stderr="")
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=f"Error response from daemon: No such container: {container_id}",
        )

    result = batch.inspect_osworld_provider_containers(
        vm, docker_cli="docker", command_runner=run
    )
    assert result["probe_succeeded"] is False
    assert result["error"] == "docker_inspect_failed_but_container_still_present"
    assert result["containers_disappeared_during_inspect"] == []


@pytest.mark.parametrize(
    ("mode", "expected_error"),
    [
        ("context_changed", "docker_context_changed_during_container_inspect"),
        ("relist_failed", "daemon unavailable"),
        (
            "ambiguous_relist",
            "docker_disappearance_recheck_ambiguous_or_truncated_container_id",
        ),
    ],
)
def test_container_disappearance_recheck_failures_are_fail_closed(
    tmp_path, mode, expected_error
):
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"qcow")
    container_id = "7" * 64
    calls = {"context": 0, "list": 0}

    def run(command, **_kwargs):
        if command[1:3] == ["context", "show"]:
            calls["context"] += 1
            context = (
                "other-context"
                if mode == "context_changed" and calls["context"] == 2
                else "desktop-linux"
            )
            return SimpleNamespace(returncode=0, stdout=f"{context}\n", stderr="")
        if command[2:6] == ["ls", "--all", "--quiet", "--no-trunc"]:
            calls["list"] += 1
            if calls["list"] == 1:
                return SimpleNamespace(
                    returncode=0, stdout=f"{container_id}\n", stderr=""
                )
            if mode == "relist_failed":
                return SimpleNamespace(
                    returncode=1, stdout="", stderr="daemon unavailable"
                )
            if mode == "ambiguous_relist":
                return SimpleNamespace(returncode=0, stdout="truncated-id\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=f"Error response from daemon: No such container: {container_id}",
        )

    result = batch.inspect_osworld_provider_containers(
        vm, docker_cli="docker", command_runner=run
    )
    assert result["probe_succeeded"] is False
    assert result["error"] == expected_error
    assert result["containers_disappeared_during_inspect"] == []


def test_container_inspect_record_must_match_requested_full_id(tmp_path):
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"qcow")
    requested_id = "5" * 64

    def run(command, **_kwargs):
        if command[1:3] == ["context", "show"]:
            return SimpleNamespace(returncode=0, stdout="desktop-linux\n", stderr="")
        if command[2:6] == ["ls", "--all", "--quiet", "--no-trunc"]:
            return SimpleNamespace(returncode=0, stdout=f"{requested_id}\n", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"Id": "6" * 64, "Image": "unrelated"}]),
            stderr="",
        )

    result = batch.inspect_osworld_provider_containers(
        vm, docker_cli="docker", command_runner=run
    )
    assert result["probe_succeeded"] is False
    assert result["error"] == "docker_single_inspect_invalid"


def test_port_allocation_adapter_ignores_concurrently_removed_containers():
    class NotFound(Exception):
        pass

    class DockerProvider:
        def _get_used_ports(self):
            return set()

    removed = SimpleNamespace()

    class RemovedAttrs:
        @property
        def attrs(self):
            raise NotFound()

    removed = RemovedAttrs()
    existing = SimpleNamespace(
        attrs={"NetworkSettings": {"Ports": {"8006/tcp": [{"HostPort": "8123"}]}}}
    )
    calls = []
    provider_module = SimpleNamespace(
        DockerProvider=DockerProvider,
        psutil=SimpleNamespace(
            net_connections=lambda: [SimpleNamespace(laddr=SimpleNamespace(port=9000))]
        ),
        docker=SimpleNamespace(errors=SimpleNamespace(NotFound=NotFound)),
    )
    original, state = install_docker_port_allocation_race_adapter(provider_module)
    try:
        instance = DockerProvider()
        instance.client = SimpleNamespace(
            containers=SimpleNamespace(
                list=lambda **kwargs: calls.append(kwargs) or [removed, existing]
            )
        )
        assert instance._get_used_ports() == {9000, 8123}
        assert calls == [{"ignore_removed": True}]
        assert state["not_found_skipped"] == 1
    finally:
        DockerProvider._get_used_ports = original


def test_direct_cleanup_verification_rejects_residual_and_accepts_not_found():
    class NotFound(Exception):
        pass

    class Containers:
        def __init__(self, residual):
            self.residual = residual

        def get(self, _container_id):
            if self.residual:
                return object()
            raise NotFound()

    def factory(residual):
        return lambda: SimpleNamespace(
            containers=Containers(residual),
            not_found_error=NotFound,
            close=lambda: None,
        )

    assert verify_docker_containers_absent(
        ["container"], client_factory=factory(False)
    )["passed"] is True
    rejected = verify_docker_containers_absent(
        ["container"], client_factory=factory(True)
    )
    assert rejected["passed"] is False
    assert rejected["residual_container_ids"] == ["container"]
