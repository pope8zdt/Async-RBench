from __future__ import annotations

import copy
from argparse import Namespace
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from filelock import FileLock, Timeout

from async_rbench.native_runtime_registry import (
    MARBLE_NATIVE_INITIALIZATION_PROFILE,
    NATIVE_ENVIRONMENT_INITIALIZATION_STATUS,
    NATIVE_RUNTIME_READY_STATUS,
    OSWORLD_NATIVE_PROFILE,
)
from async_rbench.osworld_runtime import (
    OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
    osworld_provider_lock_path,
)
from scripts.sync_source_native_runtime import (
    OSWorldBatchLockUnavailable,
    SourceNativeSyncLockUnavailable,
    exclusive_osworld_batch_snapshot_lock,
    exclusive_source_native_sync_lock,
    require_complete_benchmark_tier,
    run_sync,
    validate_osworld_full_batch_report,
    validate_source_bound_native_evidence,
)


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _record_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _runtime_files(repository_root: Path) -> dict[str, Path]:
    files = {
        "marble_lock": repository_root / "configs/marble-native-requirements.lock",
        "marble_lock_artifact": (
            repository_root
            / "artifacts/native-runtime-v4/marble_native_dependencies.lock"
        ),
        "marble_bootstrap": (
            repository_root / "artifacts/native-runtime-v4/marble_bootstrap_report.json"
        ),
        "osworld_asset": (
            repository_root
            / "artifacts/native-runtime-v4/osworld-assets/asset_attestation.json"
        ),
        "osworld_bootstrap": (
            repository_root
            / ".venv-osworld-native/osworld-native-bootstrap-report.json"
        ),
        "osworld_lock": (repository_root / "configs/osworld-native-requirements.lock"),
        "osworld_vm": (
            repository_root / "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
        ),
    }
    for name, path in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = b"marble-lock\n" if name.startswith("marble_lock") else name.encode()
        path.write_bytes(payload)
    return files


def _build_marble_cases(repository_root: Path):
    source_root = repository_root / "artifacts/source-native-v4"
    records = [
        {"scenario": "coding", "task_id": 1, "task": {"content": "one"}},
        {"scenario": "coding", "task_id": 2, "task": {"content": "two"}},
    ]
    source_path = (
        repository_root / "upstream/marble/multiagentbench/coding/coding_main.jsonl"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    runtime_files = _runtime_files(repository_root)
    built = []
    for index, record in enumerate(records, 1):
        case_id = f"mab-source-binding-{index}"
        source_task_id = f"coding:{index:03d}"
        native_path = f"cases/multiagentbench/{case_id}"
        case_dir = source_root / native_path
        case_dir.mkdir(parents=True, exist_ok=True)
        config = f"scenario: coding\ntask_id: {index}\n"
        (case_dir / "native_config.yaml").write_text(config, encoding="utf-8")
        _write_json(case_dir / "official_task.json", record)
        spec = {
            "case_id": case_id,
            "benchmark": "MultiAgentBench",
            "source_binding": {
                "task_id": source_task_id,
                "scenario": "coding",
                "jsonl_path": "upstream/marble/multiagentbench/coding/coding_main.jsonl",
                "line_number": index,
                "record_sha256": _record_sha256(record),
            },
        }
        _write_json(case_dir / "native_case.json", spec)
        row = {
            "case_id": case_id,
            "benchmark": "MultiAgentBench",
            "source_task_id": source_task_id,
            "native_path": native_path,
        }
        evidence = {
            "case_id": case_id,
            "benchmark": "MultiAgentBench",
            "source_task_id": source_task_id,
            "scenario": "coding",
            "status": NATIVE_ENVIRONMENT_INITIALIZATION_STATUS,
            "qualification_profile": MARBLE_NATIVE_INITIALIZATION_PROFILE,
            "source_evidence": {
                "jsonl_path": "upstream/marble/multiagentbench/coding/coding_main.jsonl",
                "line_number": index,
                "record_sha256": _record_sha256(record),
                "native_config_sha256": _sha256(case_dir / "native_config.yaml"),
                "native_case_sha256": _sha256(case_dir / "native_case.json"),
                "official_task_sha256": _sha256(case_dir / "official_task.json"),
            },
            "runtime_binding": {
                "dependency_lock_path": "configs/marble-native-requirements.lock",
                "dependency_lock_sha256": _sha256(runtime_files["marble_lock"]),
                "dependency_lock_artifact_path": (
                    "artifacts/native-runtime-v4/marble_native_dependencies.lock"
                ),
                "dependency_lock_artifact_sha256": _sha256(
                    runtime_files["marble_lock_artifact"]
                ),
                "bootstrap_report_path": (
                    "artifacts/native-runtime-v4/marble_bootstrap_report.json"
                ),
                "bootstrap_report_sha256": _sha256(runtime_files["marble_bootstrap"]),
            },
        }
        built.append((row, evidence))
    return source_root, built


def _build_osworld_cases(repository_root: Path):
    source_root = repository_root / "artifacts/source-native-v4"
    runtime_files = _runtime_files(repository_root)
    upstream_root = repository_root / "upstream/osworld"
    provider_sources = {
        "factory": upstream_root / "desktop_env/providers/__init__.py",
        "provider": upstream_root / "desktop_env/providers/docker/provider.py",
        "manager": upstream_root / "desktop_env/providers/docker/manager.py",
        "desktop_env": upstream_root / "desktop_env/desktop_env.py",
        "setup": upstream_root / "desktop_env/controllers/setup.py",
        "metrics": upstream_root / "desktop_env/evaluators/metrics/__init__.py",
        "getters": upstream_root / "desktop_env/evaluators/getters/__init__.py",
    }
    for name, path in provider_sources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# pinned OSWorld {name}\n", encoding="utf-8")
    subprocess.run(
        ["git", "init", "--quiet"], cwd=upstream_root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "source-binding@example.invalid"],
        cwd=upstream_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Source Binding Test"],
        cwd=upstream_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "desktop_env"],
        cwd=upstream_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "pinned OSWorld sources"],
        cwd=upstream_root,
        check=True,
        capture_output=True,
    )
    upstream_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    built = []
    for index in (1, 2):
        task_id = f"task-{index}"
        case_id = f"osw-source-binding-{index}"
        source_task_id = f"osworld:calc:{task_id}"
        evaluator = {
            "func": f"metric_{index}",
            "result": {"type": "vm_file", "path": f"/tmp/{index}"},
            "postconfig": [{"type": "sleep", "parameters": {"seconds": index}}],
        }
        task = {
            "id": task_id,
            "instruction": f"task {index}",
            "snapshot": "libreoffice_calc",
            "config": [{"type": "sleep", "parameters": {"seconds": 0}}],
            "evaluator": evaluator,
        }
        config_relative = (
            f"upstream/osworld/evaluation_examples/examples/calc/{task_id}.json"
        )
        config_path = repository_root / config_relative
        _write_json(config_path, task)
        native_path = f"cases/osworld/{case_id}"
        case_dir = source_root / native_path
        case_dir.mkdir(parents=True, exist_ok=True)
        spec = {
            "case_id": case_id,
            "benchmark": "OSWorld",
            "source_binding": {
                "task_id": task_id,
                "domain": "calc",
                "config_path": config_relative,
                "config_sha256": _sha256(config_path),
                "upstream_revision": upstream_revision,
            },
            "native_evaluator": evaluator,
        }
        _write_json(case_dir / "native_case.json", spec)
        row = {
            "case_id": case_id,
            "benchmark": "OSWorld",
            "source_task_id": source_task_id,
            "native_path": native_path,
        }
        phase_hashes = {
            "first_reset_task_setup": _canonical(task["config"]),
            "official_evaluator_postconfig": _canonical(evaluator["postconfig"]),
            "second_reset_task_setup": _canonical(task["config"]),
        }
        evidence = {
            "case_id": case_id,
            "benchmark": "OSWorld",
            "source_task_id": source_task_id,
            "status": NATIVE_RUNTIME_READY_STATUS,
            "qualification_profile": OSWORLD_NATIVE_PROFILE,
            "official_task_config_sha256": _sha256(config_path),
            "official_evaluator_source_sha256": _canonical(evaluator),
            "evaluator_probe": {
                "task_evaluator_sha256": _canonical(evaluator),
                "evaluator_func": evaluator["func"],
            },
            "setup_probe": {
                "calls": [
                    {"phase": phase, "config_sha256": digest}
                    for phase, digest in phase_hashes.items()
                ]
            },
            "provider_preflight": {
                "details": {
                    "asset_attestation_path": (
                        "artifacts/native-runtime-v4/osworld-assets/asset_attestation.json"
                    ),
                    "asset_attestation_sha256": _sha256(runtime_files["osworld_asset"]),
                    "factory_sha256": _sha256(provider_sources["factory"]),
                    "provider_source_sha256": _sha256(provider_sources["provider"]),
                    "manager_source_sha256": _sha256(provider_sources["manager"]),
                    "python_bootstrap_report_path": (
                        ".venv-osworld-native/osworld-native-bootstrap-report.json"
                    ),
                    "python_bootstrap_report_sha256": _sha256(
                        runtime_files["osworld_bootstrap"]
                    ),
                    "python_environment_lock_path": (
                        "configs/osworld-native-requirements.lock"
                    ),
                    "python_environment_lock_sha256": _sha256(
                        runtime_files["osworld_lock"]
                    ),
                    "vm_disk_path": (
                        "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
                    ),
                }
            },
        }
        built.append((row, evidence))
    return source_root, built


def test_osworld_source_binding_rejects_upstream_implementation_drift(tmp_path):
    repository_root = tmp_path / "repo"
    source_root, cases = _build_osworld_cases(repository_root)
    row, evidence = cases[0]
    provider = (
        repository_root / "upstream/osworld/desktop_env/providers/docker/provider.py"
    )
    provider.write_text("# locally modified provider\n", encoding="utf-8")

    with pytest.raises(ValueError, match="implementation tree differs"):
        validate_source_bound_native_evidence(
            evidence,
            row,
            source_root=source_root,
            repository_root=repository_root,
        )


def test_source_binding_accepts_current_osworld_and_marble_evidence(tmp_path):
    repository_root = tmp_path / "repo"
    marble_root, marble = _build_marble_cases(repository_root)
    osworld_root, osworld = _build_osworld_cases(repository_root)
    assert marble_root == osworld_root

    validate_source_bound_native_evidence(
        marble[0][1],
        marble[0][0],
        source_root=marble_root,
        repository_root=repository_root,
    )
    validate_source_bound_native_evidence(
        osworld[0][1],
        osworld[0][0],
        source_root=osworld_root,
        repository_root=repository_root,
    )


@pytest.mark.parametrize("benchmark", ["MultiAgentBench", "OSWorld"])
def test_source_binding_rejects_evidence_cloned_to_another_case(tmp_path, benchmark):
    repository_root = tmp_path / "repo"
    if benchmark == "MultiAgentBench":
        source_root, cases = _build_marble_cases(repository_root)
    else:
        source_root, cases = _build_osworld_cases(repository_root)
    _first_row, first_evidence = cases[0]
    second_row, _second_evidence = cases[1]
    cloned = copy.deepcopy(first_evidence)
    for field in ("case_id", "benchmark", "source_task_id"):
        cloned[field] = second_row[field]

    with pytest.raises(ValueError, match="not case-bound"):
        validate_source_bound_native_evidence(
            cloned,
            second_row,
            source_root=source_root,
            repository_root=repository_root,
        )

    nested_field = (
        "native_environment_initialization"
        if benchmark == "MultiAgentBench"
        else "native_environment"
    )
    nested = {
        "case_id": second_row["case_id"],
        "benchmark": second_row["benchmark"],
        "source_task_id": second_row["source_task_id"],
        "status": "environment_smoke_validated",
        nested_field: cloned,
    }
    with pytest.raises(ValueError, match="not case-bound"):
        validate_source_bound_native_evidence(
            nested,
            second_row,
            source_root=source_root,
            repository_root=repository_root,
        )


def test_sync_rejects_cloned_native_evidence_before_any_write(tmp_path):
    repository_root = tmp_path / "repo"
    source_root, cases = _build_marble_cases(repository_root)
    _first_row, first_evidence = cases[0]
    second_row, _second_evidence = cases[1]
    cloned = copy.deepcopy(first_evidence)
    for field in ("case_id", "benchmark", "source_task_id"):
        cloned[field] = second_row[field]

    manifest_path = source_root / "native_manifest.jsonl"
    report_path = source_root / "production_report.json"
    registry_path = (
        repository_root / "artifacts/native-runtime-v4/runtime_registry.jsonl"
    )
    evidence_path = repository_root / "cloned-evidence.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(second_row, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_path.write_text('{"spec_ready_count": 1}\n', encoding="utf-8")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_bytes(b"")
    _write_json(evidence_path, cloned)
    before = {
        path: path.read_bytes() for path in (manifest_path, report_path, registry_path)
    }

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/sync_source_native_runtime.py"),
            "--root",
            str(source_root),
            "--runtime-registry",
            str(registry_path),
            "--repository-root",
            str(repository_root),
            "--merge-evidence",
            str(evidence_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 2
    assert "sync_rejected" in completed.stdout
    assert "not case-bound" in completed.stdout
    assert {
        path: path.read_bytes() for path in (manifest_path, report_path, registry_path)
    } == before


def test_sync_rejects_cloned_evidence_with_unknown_case_id_before_any_write(tmp_path):
    repository_root = tmp_path / "repo"
    source_root, cases = _build_marble_cases(repository_root)
    manifest_row, first_evidence = cases[0]
    cloned = copy.deepcopy(first_evidence)
    cloned["case_id"] = "mab-source-binding-invented"

    manifest_path = source_root / "native_manifest.jsonl"
    report_path = source_root / "production_report.json"
    registry_path = (
        repository_root / "artifacts/native-runtime-v4/runtime_registry.jsonl"
    )
    evidence_path = repository_root / "cloned-evidence.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest_row, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_path.write_text('{"spec_ready_count": 1}\n', encoding="utf-8")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_bytes(b"")
    _write_json(evidence_path, cloned)
    before = {
        path: path.read_bytes() for path in (manifest_path, report_path, registry_path)
    }

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/sync_source_native_runtime.py"),
            "--root",
            str(source_root),
            "--runtime-registry",
            str(registry_path),
            "--repository-root",
            str(repository_root),
            "--merge-evidence",
            str(evidence_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 2
    assert "sync_rejected" in completed.stdout
    assert "absent from the source-native manifest" in completed.stdout
    assert {
        path: path.read_bytes() for path in (manifest_path, report_path, registry_path)
    } == before


def test_require_initialized_benchmark_accepts_exact_full_coverage():
    manifest = [
        {"case_id": "m1", "benchmark": "MultiAgentBench"},
        {"case_id": "m2", "benchmark": "MultiAgentBench"},
        {"case_id": "o1", "benchmark": "OSWorld"},
    ]
    require_complete_benchmark_tier(
        manifest,
        "MultiAgentBench",
        {"MultiAgentBench": 2},
        tier_label="native-environment-initialized",
    )


@pytest.mark.parametrize(
    ("benchmark", "counts", "message"),
    [
        (
            "MultiAgentBench",
            {"MultiAgentBench": 1},
            "not fully native-environment-initialized: MultiAgentBench \\(1/2\\)",
        ),
        ("MissingBench", {}, "required benchmark is absent from manifest"),
    ],
)
def test_require_initialized_benchmark_rejects_incomplete_or_absent(
    benchmark, counts, message
):
    manifest = [
        {"case_id": "m1", "benchmark": "MultiAgentBench"},
        {"case_id": "m2", "benchmark": "MultiAgentBench"},
    ]
    with pytest.raises(ValueError, match=message):
        require_complete_benchmark_tier(
            manifest,
            benchmark,
            counts,
            tier_label="native-environment-initialized",
        )


def _osworld_live_phase(*, postflight: bool, provider_lock_path: Path) -> dict:
    identity = {
        "id": "daemon-id",
        "name": "daemon-name",
        "server_version": "1.2.3",
        "docker_root_dir": "/var/lib/docker",
        "os_type": "linux",
        "architecture": "x86_64",
    }
    sdk_checks = {
        "ping_succeeded": True,
        "daemon_identity_complete": True,
        "official_images_match": True,
        "minimal_container_created": True,
        "exact_vm_file_bind_read_only": True,
        "kvm_or_tcg_probe_succeeded": True,
        "minimal_container_cleanup_succeeded": True,
    }
    value = {
        "validated": True,
        "provider": {
            "provider": "docker",
            "configuration_resolved": True,
            "launch_ready": True,
            "launch_attempted": False,
            "launch_succeeded": False,
            "blockers": [],
            "details": {
                "daemon_reachable": True,
                "docker_image_present": True,
                "docker_digest_image_present": True,
                "docker_latest_image_present": True,
                "docker_image_identity": OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
                "docker_digest_image_identity": OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
                "docker_latest_image_identity": OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
                "vm_disk_present": True,
                "asset_attestation_verified": True,
                "python_bootstrap_verified": True,
            },
        },
        "kvm_probe": {"device_available": True, "exit_code": 0},
        "docker_cli_daemon": {
            "probe_succeeded": True,
            "context": "desktop-linux",
            "daemon_identity": identity,
        },
        "docker_sdk_provider": {
            "probe_succeeded": True,
            "ping_succeeded": True,
            "daemon_identity": identity,
            "client_base_url": "http+docker://localnpipe",
            "image_identities": {
                "untagged": OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
                "digest": OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
                "latest": OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
            },
            "minimal_container_probe": {
                "attempted": True,
                "created": True,
                "mount_read_only": True,
                "exit_code": 0,
                "cleanup_attempted": True,
                "cleanup_succeeded": True,
                "residual_container_present": False,
            },
            "checks": sdk_checks,
        },
        "daemon_identity_matches": True,
        "container_probe": {
            "probe_succeeded": True,
            "official_container_ids": [],
            "provider_container_ids": [],
            "containers": [],
        },
        "provider_vm_lock": {
            "path": str(provider_lock_path),
            "acquired": True,
            "error": "",
        },
    }
    if postflight:
        value["preflight_postflight_identity_stable"] = True
    return value


def _write_osworld_batch_gate_fixture(repository_root: Path):
    batch_root = repository_root / "artifacts/native-runtime-v4/osworld-native"
    cases_root = batch_root / "cases"
    cases_root.mkdir(parents=True)
    manifest = []
    registry = {}
    results = []
    for index in range(91):
        case_id = f"osw-gate-{index:03d}"
        source_task_id = f"osworld:test:{index:03d}"
        evidence = {
            "case_id": case_id,
            "benchmark": "OSWorld",
            "source_task_id": source_task_id,
            "status": NATIVE_RUNTIME_READY_STATUS,
            "evidence_sha256": hashlib.sha256(case_id.encode()).hexdigest(),
        }
        evidence_path = cases_root / f"{case_id}.json"
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest.append(
            {
                "case_id": case_id,
                "benchmark": "OSWorld",
                "source_task_id": source_task_id,
            }
        )
        registry[case_id] = evidence
        results.append(
            {
                "case_id": case_id,
                "return_code": 0,
                "status": NATIVE_RUNTIME_READY_STATUS,
                "qualified": True,
                "reason": None,
                "evidence_path": str(evidence_path.resolve()),
                "evidence_file_sha256": _sha256(evidence_path),
                "skipped_already_valid": True,
                "duration_seconds": 0.0,
            }
        )
    report = {
        "schema_version": "osworld-native-batch-v1",
        "status": NATIVE_RUNTIME_READY_STATUS,
        "full_collection_requested": True,
        "expected_full_collection_count": 91,
        "discovered_case_count": 91,
        "unique_case_count": 91,
        "selected_case_count": 91,
        "all_91_selected": True,
        "all_91_explicitly_selected": True,
        "full_collection_validated": True,
        "native_environment_validated_count": 91,
        "failed_count": 0,
        "registry_merged": False,
        "atomic_sync_required": True,
        "status_required": NATIVE_RUNTIME_READY_STATUS,
        "sync_command": (
            "python scripts/sync_source_native_runtime.py --merge-evidence "
            "artifacts/native-runtime-v4/osworld-native "
            "--require-ready-benchmark OSWorld"
        ),
        "live_provider_preflight": _osworld_live_phase(
            postflight=False,
            provider_lock_path=osworld_provider_lock_path(
                repository_root
                / "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
            ),
        ),
        "live_provider_postflight": _osworld_live_phase(
            postflight=True,
            provider_lock_path=osworld_provider_lock_path(
                repository_root
                / "artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2"
            ),
        ),
        "results": results,
    }
    report_path = batch_root / "batch_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest, registry, report, report_path


def test_osworld_ready_gate_requires_canonical_validated_batch_envelope(tmp_path):
    manifest, registry, _report, _report_path = _write_osworld_batch_gate_fixture(
        tmp_path
    )
    validate_osworld_full_batch_report(
        manifest,
        registry,
        repository_root=tmp_path,
    )


def test_osworld_ready_gate_rejects_report_to_case_hash_mismatch(tmp_path):
    manifest, registry, report, report_path = _write_osworld_batch_gate_fixture(
        tmp_path
    )
    report["results"][0]["evidence_file_sha256"] = "0" * 64
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="batch result is not promotable"):
        validate_osworld_full_batch_report(
            manifest,
            registry,
            repository_root=tmp_path,
        )


def test_osworld_ready_gate_rejects_postflight_daemon_switch(tmp_path):
    manifest, registry, report, report_path = _write_osworld_batch_gate_fixture(
        tmp_path
    )
    report["live_provider_postflight"]["docker_sdk_provider"][
        "client_base_url"
    ] = "http+docker://different-daemon"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="provider changed"):
        validate_osworld_full_batch_report(
            manifest,
            registry,
            repository_root=tmp_path,
        )


def test_osworld_ready_gate_rejects_direct_case_not_bound_to_registry(tmp_path):
    manifest, registry, _report, _report_path = _write_osworld_batch_gate_fixture(
        tmp_path
    )
    registry[manifest[0]["case_id"]] = {
        **registry[manifest[0]["case_id"]],
        "evidence_sha256": "f" * 64,
    }

    with pytest.raises(ValueError, match="does not match the merged registry"):
        validate_osworld_full_batch_report(
            manifest,
            registry,
            repository_root=tmp_path,
        )


def _sync_lock_probe(repository_root: Path) -> subprocess.CompletedProcess[str]:
    code = """
from pathlib import Path
import sys
from scripts.sync_source_native_runtime import (
    SourceNativeSyncLockUnavailable,
    exclusive_source_native_sync_lock,
)

try:
    with exclusive_source_native_sync_lock(Path(sys.argv[1])):
        print("acquired")
except SourceNativeSyncLockUnavailable:
    print("locked")
    raise SystemExit(23)
"""
    return subprocess.run(
        [sys.executable, "-c", code, str(repository_root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_source_native_sync_lock_serializes_processes_and_releases(tmp_path):
    with exclusive_source_native_sync_lock(tmp_path):
        rejected = _sync_lock_probe(tmp_path)

    acquired = _sync_lock_probe(tmp_path)
    assert rejected.returncode == 23
    assert rejected.stdout.strip() == "locked"
    assert acquired.returncode == 0
    assert acquired.stdout.strip() == "acquired"


def test_sync_cli_rejects_lock_contention_before_repository_writes(tmp_path):
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    with exclusive_source_native_sync_lock(tmp_path):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/sync_source_native_runtime.py"),
                "--repository-root",
                str(tmp_path),
                "--root",
                str(tmp_path / "missing-source-root"),
                "--runtime-registry",
                str(tmp_path / "missing-registry.jsonl"),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    assert completed.returncode == 2
    assert "sync_rejected" in completed.stdout
    assert "already running" in completed.stdout
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_osworld_snapshot_lock_interoperates_with_batch_filelock(tmp_path):
    lock_path = (
        tmp_path
        / "artifacts/native-runtime-v4/osworld-native/.osworld-native-batch.lock"
    )
    batch_lock = FileLock(str(lock_path))
    with batch_lock.acquire(timeout=0):
        with pytest.raises(OSWorldBatchLockUnavailable):
            with exclusive_osworld_batch_snapshot_lock(tmp_path):
                pass

    with exclusive_osworld_batch_snapshot_lock(tmp_path):
        with pytest.raises(Timeout):
            batch_lock.acquire(timeout=0)


def test_osworld_native_promotion_gate_is_not_opt_in(tmp_path, monkeypatch):
    source_root = tmp_path / "artifacts/source-native-v4"
    manifest_path = source_root / "native_manifest.jsonl"
    report_path = source_root / "production_report.json"
    registry_path = tmp_path / "artifacts/native-runtime-v4/runtime_registry.jsonl"
    evidence_path = tmp_path / "direct-osworld-evidence.json"
    row = {
        "case_id": "direct-osworld-case",
        "benchmark": "OSWorld",
        "source_task_id": "osworld:test:direct",
    }
    evidence = {
        **row,
        "status": NATIVE_RUNTIME_READY_STATUS,
        "evidence_sha256": "a" * 64,
    }
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    report_path.write_text("{}\n", encoding="utf-8")
    registry_path.parent.mkdir(parents=True)
    registry_path.write_bytes(b"")
    evidence_path.write_text(json.dumps(evidence) + "\n", encoding="utf-8")
    before = {
        path: path.read_bytes() for path in (manifest_path, report_path, registry_path)
    }

    monkeypatch.setattr(
        "scripts.sync_source_native_runtime.validate_registry_source_bindings",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "scripts.sync_source_native_runtime.synchronize_runtime_metadata",
        lambda manifest, report, _registry, **_kwargs: (
            manifest,
            report,
            {
                "runtime_ready_benchmark_counts": {"OSWorld": 1},
                "native_environment_initialization_benchmark_counts": {},
                "environment_smoke_ready_benchmark_counts": {},
            },
        ),
    )
    args = Namespace(
        root=str(source_root),
        runtime_registry=str(registry_path),
        repository_root=str(tmp_path),
        merge_evidence=[str(evidence_path)],
        check=False,
        require_ready_benchmark=[],
        require_initialized_benchmark=[],
        require_smoke_ready_benchmark=[],
    )

    with pytest.raises(ValueError, match="exact 91-case collection"):
        run_sync(args)

    assert {
        path: path.read_bytes() for path in (manifest_path, report_path, registry_path)
    } == before
