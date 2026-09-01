import copy
import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from async_rbench.native_runtime_registry import (
    ENVIRONMENT_SMOKE_READY_STATUS,
    environment_smoke_qualification,
)
from async_rbench.osworld_runtime import (
    LocalOSWorldEnvironment,
    OSWorldDispatchCatalog,
    RealVMRequiredError,
    RuntimePhase,
    load_osworld_cases,
    probe_real_vm_provider,
    qualify_environment_smoke,
    validate_osworld_asset_attestation,
    validate_osworld_python_bootstrap,
)
import async_rbench.osworld_runtime as osworld_runtime_module
import scripts.run_osworld_native_batch as osworld_batch_module
from scripts.run_osworld_native_case import (
    DEFAULT_OSWORLD_VM_PATH as CASE_DEFAULT_OSWORLD_VM_PATH,
    SetupCallTracer,
    canonical_digest,
    execute_official_evaluator,
    install_docker_kvm_provider_adapter,
)
from scripts.run_osworld_native_batch import (
    DEFAULT_OSWORLD_VM_PATH as BATCH_DEFAULT_OSWORLD_VM_PATH,
    EXPECTED_OSWORLD_CASE_COUNT,
    exact_full_collection_selected,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def osworld_cases():
    return load_osworld_cases(ROOT)


@pytest.fixture(scope="module")
def dispatch_identity():
    return OSWorldDispatchCatalog(ROOT / "upstream" / "osworld").source_identity()


@pytest.fixture(scope="module")
def provider_probe():
    return probe_real_vm_provider(ROOT / "upstream" / "osworld", provider="docker")


def test_all_91_cases_bind_to_official_setup_getter_and_metric_dispatch(osworld_cases):
    assert len(osworld_cases) == 91
    assert len({case.case_id for case in osworld_cases}) == 91
    assert len({case.source_task_id for case in osworld_cases}) == 91
    assert sum(case.is_infeasible for case in osworld_cases) == 3
    for case in osworld_cases:
        assert case.config_path.is_file()
        assert case.dispatch.metric_functions
        assert case.dispatch.evaluator_sha256


def test_direct_and_batch_launchers_share_the_attested_vm_default():
    assert CASE_DEFAULT_OSWORLD_VM_PATH == BATCH_DEFAULT_OSWORLD_VM_PATH
    assert CASE_DEFAULT_OSWORLD_VM_PATH == (
        "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
    )


def test_native_batch_all_requires_the_exact_duplicate_free_91_case_collection(
    tmp_path, monkeypatch
):
    assert exact_full_collection_selected(
        full_collection_requested=True,
        discovered_case_count=EXPECTED_OSWORLD_CASE_COUNT,
        unique_case_count=EXPECTED_OSWORLD_CASE_COUNT,
        selected_case_count=EXPECTED_OSWORLD_CASE_COUNT,
    ) is True
    assert exact_full_collection_selected(
        full_collection_requested=True,
        discovered_case_count=EXPECTED_OSWORLD_CASE_COUNT - 1,
        unique_case_count=EXPECTED_OSWORLD_CASE_COUNT - 1,
        selected_case_count=EXPECTED_OSWORLD_CASE_COUNT - 1,
    ) is False

    incomplete_cases = [
        SimpleNamespace(case_id=f"case-{index}")
        for index in range(EXPECTED_OSWORLD_CASE_COUNT - 1)
    ]
    output = tmp_path / "batch"
    monkeypatch.setattr(
        osworld_batch_module,
        "load_osworld_cases",
        lambda *args, **kwargs: incomplete_cases,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_osworld_native_batch.py", "--all", "--output", str(output)],
    )
    assert osworld_batch_module.main() == 2
    report = json.loads((output / "batch_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "blocked_full_collection_selection"
    assert report["full_collection_requested"] is True
    assert report["selected_case_count"] == EXPECTED_OSWORLD_CASE_COUNT - 1
    assert report["all_91_selected"] is False
    assert report["full_collection_validated"] is False


def test_every_osworld_case_starts_resets_changes_state_and_scores_control_path(
    tmp_path, osworld_cases, dispatch_identity, provider_probe
):
    entries = []
    for case in osworld_cases:
        entry = qualify_environment_smoke(
            case,
            tmp_path / case.case_id,
            provider_probe=provider_probe,
            dispatch_identity=dispatch_identity,
        )
        entries.append(entry)
        assert entry["status"] == ENVIRONMENT_SMOKE_READY_STATUS
        assert entry["execution_scope"] == "infrastructure_smoke"
        assert entry["environment"]["real_vm"] is False
        assert entry["checks"]["official_gold_metric_executed"] is False
        assert entry["checkpoint_smoke"]["baseline_revision"] != entry["checkpoint_smoke"]["checkpoint_revision"]
        assert entry["checkpoint_smoke"]["baseline_revision"] == entry["checkpoint_smoke"]["restored_revision"]
        assert environment_smoke_qualification(
            entry,
            benchmark="OSWorld",
            source_task_id=case.source_task_id,
        ) == (True, None)
    assert sum(entry["score_probe"]["score"] == 1.0 for entry in entries) == 3
    assert sum(entry["score_probe"]["score"] == 0.0 for entry in entries) == 88


def test_local_runtime_rejects_desktop_actions_and_gold_scoring(tmp_path, osworld_cases):
    case = next(case for case in osworld_cases if not case.is_infeasible)
    env = LocalOSWorldEnvironment(case, tmp_path / "runtime")
    env.start()
    env.reset()
    baseline = env.state_revision
    with pytest.raises(RealVMRequiredError, match="real OSWorld VM"):
        env.step("pyautogui.click(10, 10)")
    assert env.state_revision == baseline
    _, _, done, info = env.step("DONE")
    assert done is True and info == {"done": True}
    with pytest.raises(RealVMRequiredError, match="gold metric"):
        env.evaluate()
    env.close()
    assert env.phase is RuntimePhase.CLOSED


def test_registry_rejects_a_smoke_entry_that_claims_real_vm(
    tmp_path, osworld_cases, dispatch_identity, provider_probe
):
    case = osworld_cases[0]
    entry = qualify_environment_smoke(
        case,
        tmp_path / case.case_id,
        provider_probe=provider_probe,
        dispatch_identity=dispatch_identity,
    )
    tampered = copy.deepcopy(entry)
    tampered["environment"]["real_vm"] = True
    assert environment_smoke_qualification(
        tampered,
        benchmark="OSWorld",
        source_task_id=case.source_task_id,
    ) == (False, "case_environment_smoke_validation_incomplete")


def test_cli_can_qualify_one_case_without_mutating_shared_registry(tmp_path, osworld_cases):
    case = osworld_cases[0]
    output = tmp_path / "evidence"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "qualify_osworld_runtime.py"),
            "--case-id",
            case.case_id,
            "--output",
            str(output),
            "--no-registry-write",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["selected_case_count"] == 1
    assert report["environment_smoke_validated_count"] == 1
    assert report["real_vm_executed_count"] == 0
    assert report["registry_merged"] is False


def test_real_native_entry_point_fails_closed_without_vm_assets(tmp_path, osworld_cases):
    case = osworld_cases[0]
    missing_disk = tmp_path / "missing.qcow2"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_osworld_native_case.py"),
            "--case-id",
            case.case_id,
            "--provider",
            "docker",
            "--path-to-vm",
            str(missing_disk),
            "--preflight-only",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "blocked_real_vm_prerequisites"
    assert report["fallback_used"] is False
    assert report["real_vm_executed"] is False
    assert report["model_episode_executed"] is False
    assert "osworld_vm_disk_missing" in report["provider_preflight"]["blockers"]


def test_native_evaluator_probe_traces_case_getter_and_metric_without_terminal_action():
    class FakeDesktopEnv:
        def __init__(self):
            self.action_history = []
            self.evaluator = {
                "func": "fake_metric",
                "result": {"type": "fake"},
                "expected": {"type": "fake"},
            }
            self.result_getter = lambda environment, config: config["value"]
            self.expected_getter = lambda environment, config: config["value"]
            self.metric = lambda actual, expected: float(actual == expected)

        def evaluate(self):
            actual = self.result_getter(self, {"value": "actual"})
            expected = self.expected_getter(self, {"value": "actual"})
            return self.metric(actual, expected)

    environment = FakeDesktopEnv()
    probe = execute_official_evaluator(environment, infeasible=False)
    assert probe["official_evaluator_executed"] is True
    assert probe["score"] == 1.0
    assert probe["score_numeric_finite"] is True
    assert probe["action_history_empty_before"] is True
    assert probe["action_history_empty_after"] is True
    assert probe["result_getter_executed"] is True
    assert probe["gold_metric_executed"] is True
    assert [record["kind"] for record in probe["execution_trace"]] == [
        "result_getter", "expected_getter", "metric",
    ]
    assert all(record["completed"] is True for record in probe["execution_trace"])


def test_native_evaluator_probe_binds_pre_execution_config_when_evaluate_mutates_it():
    class MutatingDesktopEnv:
        def __init__(self):
            self.action_history = []
            self.evaluator = {
                "func": "fake_metric",
                "result": {"type": "official"},
                "expected": {"type": "official"},
            }
            self.result_getter = lambda environment, config: config["value"]
            self.expected_getter = lambda environment, config: config["value"]
            self.metric = lambda actual, expected: float(actual == expected)

        def evaluate(self):
            actual = self.result_getter(self, {"value": "same"})
            expected = self.expected_getter(self, {"value": "same"})
            self.evaluator["result"]["type"] = "runtime-mutated"
            self.evaluator["runtime_cache"] = {"created": True}
            return self.metric(actual, expected)

    environment = MutatingDesktopEnv()
    official_digest = canonical_digest(environment.evaluator)
    probe = execute_official_evaluator(environment, infeasible=False)

    assert environment.evaluator["result"]["type"] == "runtime-mutated"
    assert probe["task_evaluator_sha256"] == official_digest
    assert probe["task_evaluator_sha256"] != canonical_digest(environment.evaluator)
    assert probe["dispatch_trace_valid"] is True


def test_native_evaluator_probe_marks_infeasible_metric_not_applicable():
    class FakeInfeasibleDesktopEnv:
        def __init__(self):
            self.action_history = []
            self.evaluator = {"func": "infeasible"}
            self.result_getter = None
            self.expected_getter = None
            self.metric = lambda: 1.0

        def evaluate(self):
            return 0

    probe = execute_official_evaluator(FakeInfeasibleDesktopEnv(), infeasible=True)
    assert probe["official_evaluator_executed"] is True
    assert probe["metric_applicability"] == "not_applicable_infeasible"
    assert probe["score"] == 0.0
    assert probe["score_numeric_finite"] is True
    assert probe["result_getter_executed"] is False
    assert probe["gold_metric_executed"] is False
    assert probe["execution_trace"] == []


def test_setup_tracer_rejects_a_reset_phase_whose_last_setup_returned_false():
    class FakeSetupController:
        def setup(self, config, use_proxy=False):
            return False

    tracer = SetupCallTracer(FakeSetupController)
    tracer.install()
    try:
        tracer.set_phase("first_reset_task_setup")
        assert FakeSetupController().setup([]) is False
        result = tracer.phase_result("first_reset_task_setup")
        assert result["all_calls_completed"] is True
        assert result["last_call_returned_true"] is False
    finally:
        tracer.restore()


def test_kvm_adapter_changes_only_the_upstream_provider_module_binding():
    provider_module = SimpleNamespace(os=os)
    original_global_os = os
    original_provider_os, evidence = install_docker_kvm_provider_adapter(
        provider_module, enabled=True
    )
    try:
        assert provider_module.os is not original_global_os
        assert provider_module.os.path.exists("/dev/kvm") is True
        assert os is original_global_os
        assert evidence["global_os_patched"] is False
    finally:
        provider_module.os = original_provider_os


def test_asset_attestation_binds_path_size_mtime_hash_claim_and_docker_ids(
    tmp_path, monkeypatch
):
    qcow2 = tmp_path / "Ubuntu.qcow2"
    qcow2.write_bytes(b"attested-test-disk")
    monkeypatch.setattr(
        osworld_runtime_module, "OFFICIAL_OSWORLD_QCOW2_SIZE", qcow2.stat().st_size
    )
    attestation = tmp_path / "asset_attestation.json"
    attestation.write_text(
        json.dumps({
            "schema_version": "osworld-official-assets-v1",
            "assets_ready": True,
            "qcow2_path": str(qcow2.resolve()),
            "qcow2_size": qcow2.stat().st_size,
            "qcow2_mtime_ns": qcow2.stat().st_mtime_ns,
            "qcow2_sha256": osworld_runtime_module.OFFICIAL_OSWORLD_QCOW2_SHA256,
            "qcow2_sha256_verified": True,
            "docker_image": osworld_runtime_module.OFFICIAL_OSWORLD_DOCKER_IMAGE,
            "docker_identity": {
                "digest_image_id": osworld_runtime_module.OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
                "upstream_latest_image_id": osworld_runtime_module.OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
            },
        }),
        encoding="utf-8",
    )
    valid, blockers, details = validate_osworld_asset_attestation(
        attestation,
        qcow2,
        digest_image_id=osworld_runtime_module.OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
        latest_image_id=osworld_runtime_module.OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
    )
    assert valid is True and blockers == []
    assert details["asset_attestation_verified"] is True

    qcow2.write_bytes(b"drifted")
    valid, blockers, _ = validate_osworld_asset_attestation(
        attestation,
        qcow2,
        digest_image_id=osworld_runtime_module.OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
        latest_image_id=osworld_runtime_module.OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
    )
    assert valid is False
    assert blockers == ["osworld_asset_attestation_mismatch"]


def test_python_bootstrap_validation_fails_closed_when_report_is_missing(tmp_path):
    lock = tmp_path / "osworld-native-requirements.lock"
    lock.write_text("package==1\n", encoding="utf-8")
    valid, blockers, details = validate_osworld_python_bootstrap(
        tmp_path / "missing-report.json",
        lock,
        ROOT / "upstream" / "osworld",
    )
    assert valid is False
    assert blockers == ["osworld_python_bootstrap_report_missing"]
    assert details["python_bootstrap_verified"] is False


def _synthetic_bootstrap_report(tmp_path):
    venv = tmp_path / "venv"
    interpreter = venv / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"synthetic interpreter")
    pyvenv_cfg = venv / "pyvenv.cfg"
    pyvenv_cfg.write_text(
        "include-system-site-packages = false\nversion = 3.12.13\n",
        encoding="utf-8",
    )
    base_prefix = tmp_path / "base-python"
    base_prefix.mkdir()
    psutil_dir = venv / "Lib" / "site-packages" / "psutil"
    psutil_dir.mkdir(parents=True)
    psutil_file = psutil_dir / "__init__.py"
    psutil_file.write_text("__version__ = '5.9.8'\n", encoding="utf-8")
    psutil_binary = psutil_dir / "_psutil_windows.pyd"
    psutil_binary.write_bytes(b"synthetic pyd")

    upstream = tmp_path / "upstream" / "osworld"
    desktop_file = upstream / "desktop_env" / "desktop_env.py"
    desktop_file.parent.mkdir(parents=True)
    desktop_file.write_text("class DesktopEnv: pass\n", encoding="utf-8")
    requirements = upstream / "requirements.txt"
    requirements.write_text("package==1\n", encoding="utf-8")
    setup = upstream / "setup.py"
    setup.write_text("setup(install_requires=['package==1'])\n", encoding="utf-8")
    lock = tmp_path / "osworld-native-requirements.lock"
    lock.write_text("package==1\n", encoding="utf-8")
    snapshot = {"count": 2, "sha256": "b" * 64}
    report = {
        "schema_version": "osworld-native-python-bootstrap-v1",
        "passed": True,
        "environment_fingerprint_sha256": "a" * 64,
        "venv_path": str(venv.resolve()),
        "upstream_root": str(upstream.resolve()),
        "interpreter": {
            "executable": str(interpreter.resolve()),
            "version": "3.12.13",
            "implementation": "CPython",
            "prefix": str(venv.resolve()),
            "base_prefix": str(base_prefix.resolve()),
        },
        "isolation": {
            "include_system_site_packages": False,
            "pyvenv_cfg_sha256": hashlib.sha256(pyvenv_cfg.read_bytes()).hexdigest(),
        },
        "lock": {
            "path": str(lock.resolve()),
            "sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            "installed_distributions": {
                **snapshot,
                "duplicate_distributions": [],
            },
            "check": {
                "passed": True,
                "checked": 1,
                "unexpected_distributions": [],
                "violations": [],
            },
        },
        "installer": {"uv_version": "uv 0.11.28", "torch_backend": "cpu"},
        "upstream_constraints": {
            "passed": True,
            "checked": 2,
            "violations": [],
            "sources": {
                "requirements.txt": {
                    "path": str(requirements.resolve()),
                    "sha256": hashlib.sha256(requirements.read_bytes()).hexdigest(),
                },
                "setup.py": {
                    "path": str(setup.resolve()),
                    "sha256": hashlib.sha256(setup.read_bytes()).hexdigest(),
                },
            },
        },
        "pip_check": {"passed": True, "output": "No broken requirements found."},
        "runtime_versions": {
            "numpy": "1.26.4",
            "torch": "2.5.1+cpu",
            "opencv_python_headless": "4.8.1",
            "matplotlib": "3.7.5",
            "pandas": "2.2.3",
            "pillow": "11.0.0",
            "psutil": "5.9.8",
        },
        "imports": {
            "desktop_env": {
                "module": "desktop_env.desktop_env",
                "file": str(desktop_file.resolve()),
            },
            "psutil": {
                "version": "5.9.8",
                "file": str(psutil_file.resolve()),
                "binary_file": str(psutil_binary.resolve()),
            },
            "docker_provider": {
                "manager_module": "desktop_env.providers.docker.manager",
                "provider_module": "desktop_env.providers.docker.provider",
            },
        },
    }
    report_path = tmp_path / "bootstrap-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path, report, lock, upstream, interpreter, venv, base_prefix, snapshot


def _validate_synthetic_bootstrap(values):
    report_path, _, lock, upstream, interpreter, venv, base_prefix, snapshot = values
    return validate_osworld_python_bootstrap(
        report_path,
        lock,
        upstream,
        interpreter=interpreter,
        prefix=venv,
        base_prefix=base_prefix,
        installed_distributions_snapshot=snapshot,
    )


def test_python_bootstrap_validation_accepts_isolated_cpython312(tmp_path):
    values = _synthetic_bootstrap_report(tmp_path)
    valid, blockers, details = _validate_synthetic_bootstrap(values)
    assert valid is True
    assert blockers == []
    assert all(details["python_bootstrap_checks"].values())


@pytest.mark.parametrize(
    "drift",
    ["python313", "system_site", "lock", "psutil_escape", "distributions"],
)
def test_python_bootstrap_validation_rejects_environment_drift(tmp_path, drift):
    values = list(_synthetic_bootstrap_report(tmp_path))
    report_path, report, lock = values[:3]
    if drift == "python313":
        report["interpreter"]["version"] = "3.13.3"
    elif drift == "system_site":
        report["isolation"]["include_system_site_packages"] = True
    elif drift == "lock":
        lock.write_text("package==2\n", encoding="utf-8")
    elif drift == "psutil_escape":
        escaped = tmp_path / "outside" / "_psutil_windows.pyd"
        escaped.parent.mkdir()
        escaped.write_bytes(b"escaped")
        report["imports"]["psutil"]["binary_file"] = str(escaped.resolve())
    elif drift == "distributions":
        values[-1] = {"count": 2, "sha256": "c" * 64}
    report_path.write_text(json.dumps(report), encoding="utf-8")
    valid, blockers, details = _validate_synthetic_bootstrap(values)
    assert valid is False
    assert blockers == ["osworld_python_bootstrap_report_mismatch"]
    assert not all(details["python_bootstrap_checks"].values())
