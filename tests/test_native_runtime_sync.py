import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from async_rbench.native_runtime_registry import (
    ENVIRONMENT_SMOKE_READY_STATUS,
    INFRASTRUCTURE_SMOKE_SCOPE,
    MARBLE_NATIVE_INITIALIZATION_PROFILE,
    MARBLE_SMOKE_PROFILE,
    MODEL_EPISODE_SCOPE,
    NATIVE_ENVIRONMENT_INITIALIZATION_STATUS,
    NATIVE_RUNTIME_PROFILE_VALIDATORS,
    NATIVE_RUNTIME_READY_STATUS,
    NATIVE_RUNTIME_SCOPE,
    OSWORLD_NATIVE_PROFILE,
    OSWORLD_SMOKE_PROFILE,
    READY_STATUS,
    environment_smoke_qualification,
    merge_registry_entries,
    model_execution_validated,
    native_environment_initialization_qualification,
    qualification,
    register_native_runtime_profile,
    replace_runtime_metadata_atomically,
    serialize_runtime_metadata,
    synchronize_runtime_metadata,
)
from scripts.run_osworld_native_batch import (
    OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
    cleanup_timeout_provider_containers,
    docker_bind_source_matches_file,
    docker_cli_sdk_daemon_match,
    docker_provider_identity_stable,
    evidence_matches_current_case,
    infrastructure_failure_retryable,
    live_provider_preflight_valid,
    live_provider_postflight_valid,
    provider_containers_absent,
    probe_docker_sdk_provider,
    qualify_entry_safely,
    reusable_evidence,
    write_json as write_batch_json,
)


def smoke(case_id="c1", benchmark="OSWorld", source_task_id="source-1"):
    return {
        "case_id": case_id,
        "benchmark": benchmark,
        "source_task_id": source_task_id,
        "status": ENVIRONMENT_SMOKE_READY_STATUS,
        "qualification_profile": OSWORLD_SMOKE_PROFILE,
        "execution_scope": INFRASTRUCTURE_SMOKE_SCOPE,
        "checks": {
            "official_config_bound": True,
            "upstream_dispatch_bound": True,
            "provider_launch_configuration_resolved": True,
            "local_runtime_started": True,
            "reset_reproducible": True,
            "local_state_changed": True,
            "evaluator_control_path_scored": True,
            "audit_chain_valid": True,
            "real_vm_executed": False,
            "model_episode_executed": False,
            "official_task_setup_executed": False,
            "official_gold_metric_executed": False,
        },
        "environment": {
            "adapter": "async_rbench.osworld_runtime.LocalOSWorldEnvironment",
            "scope": "infrastructure_only",
            "real_vm": False,
            "model_episode": False,
        },
        "score_probe": {
            "kind": "official_terminal_fail_control_path",
            "score": 0.0,
            "expected_score": 0.0,
            "native_metric_executed": False,
            "real_vm_executed": False,
            "model_episode": False,
        },
        "checkpoint_smoke": {
            "baseline_revision": "baseline",
            "checkpoint_revision": "changed",
            "restored_revision": "baseline",
        },
    }


def manifest_row(case_id="c1", benchmark="OSWorld", source_task_id="source-1"):
    return {
        "case_id": case_id,
        "benchmark": benchmark,
        "source_task_id": source_task_id,
        "runtime_ready": False,
        "runtime_blocker": "case_runtime_not_validated",
        "preserved": {"field": True},
    }


def canonical_digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def osworld_native():
    empty_setup_sha256 = canonical_digest([])
    task_evaluator_sha256 = canonical_digest({"func": "check_include_exclude"})
    entry = {
        "schema_version": "osworld-native-environment-v2",
        "case_id": "c1", "benchmark": "OSWorld", "source_task_id": "source-1",
        "status": NATIVE_RUNTIME_READY_STATUS, "execution_scope": NATIVE_RUNTIME_SCOPE,
        "qualification_profile": OSWORLD_NATIVE_PROFILE,
        "real_vm_executed": True, "official_task_setup_executed": True,
        "official_evaluator_executed": True,
        "official_gold_metric_executed": True, "model_episode_executed": False,
        "fallback_used": False,
        "checks": {name: True for name in (
            "real_environment_imported", "real_environment_started",
            "official_task_setup_executed", "official_evaluator_executed",
            "first_reset_task_setup_succeeded",
            "evaluator_postconfig_setup_succeeded",
            "second_reset_task_setup_succeeded",
            "evaluator_score_numeric_finite",
            "case_specific_result_getter_executed",
            "case_specific_gold_metric_executed",
            "wait_marked_environment_used", "second_reset_completed",
            "docker_container_replaced", "action_history_cleared_on_second_reset",
            "docker_kvm_probe_completed", "provider_module_adapter_consistent",
        )},
        "provider_preflight": {
            "provider": "docker", "configuration_resolved": True,
            "launch_ready": True, "launch_attempted": True,
            "launch_succeeded": True, "blockers": [],
            "details": {
                "asset_attestation_present": True,
                "asset_attestation_verified": True,
                "asset_attestation_sha256": "5" * 64,
                "asset_attestation_checks": {
                    "schema_valid": True, "assets_ready": True,
                    "qcow2_path_matches": True, "qcow2_file_present": True,
                    "qcow2_size_matches": True, "qcow2_mtime_matches": True,
                    "qcow2_hash_attested": True, "docker_digest_attested": True,
                    "docker_digest_present": True,
                    "docker_latest_matches_digest": True,
                },
                "python_bootstrap_report_present": True,
                "python_bootstrap_report_sha256": "6" * 64,
                "python_environment_lock_present": True,
                "python_environment_lock_sha256": "7" * 64,
                "python_environment_isolated": True,
                "python_pip_check_passed": True,
                "python_desktop_env_import_bound": True,
                "python_docker_provider_import_bound": True,
                "python_psutil_import_isolated": True,
                "python_bootstrap_verified": True,
                "python_bootstrap_checks": {
                    "schema_valid": True, "report_passed": True,
                    "interpreter_matches": True,
                    "interpreter_is_supported_cpython": True,
                    "interpreter_prefix_matches": True,
                    "interpreter_base_prefix_matches": True,
                    "venv_prefix_matches": True, "upstream_root_matches": True,
                    "venv_isolated": True, "lock_path_matches": True,
                    "lock_sha256_matches": True,
                    "environment_fingerprint_valid": True,
                    "installer_configuration_valid": True,
                    "installed_distributions_match": True,
                    "lock_installation_valid": True,
                    "upstream_constraints_valid": True,
                    "runtime_versions_authoritative": True,
                    "pip_check_passed": True,
                    "desktop_env_import_bound": True,
                    "psutil_import_isolated": True,
                    "docker_provider_import_bound": True,
                },
            },
        },
        "kvm_probe": {
            "attempted": True, "device_available": True, "exit_code": 0,
            "command": [
                "run", "--rm", "--device", "/dev/kvm", "--entrypoint", "sh",
                "happysixd/osworld-docker", "-c", "test -c /dev/kvm",
            ],
            "detail": "",
        },
        "runtime_compatibility_adapter": {
            "scope": "desktop_env.providers.docker.provider.os",
            "enabled": True, "kvm_exists_overridden": True,
            "provider_module_os_replaced": True, "global_os_patched": False,
            "upstream_source_modified": False, "acceleration_mode": "kvm",
        },
        "official_task_config_sha256": "3" * 64,
        "official_evaluator_source_sha256": "4" * 64,
        "setup_probe": {
            "calls": [
                {
                    "phase": phase, "config_count": 0,
                    "config_sha256": empty_setup_sha256,
                    "entered": True, "completed": True, "returned_true": True,
                }
                for phase in (
                    "first_reset_task_setup",
                    "official_evaluator_postconfig",
                    "second_reset_task_setup",
                )
            ],
            "phase_results": {
                phase: {
                    "call_count": 1, "all_calls_completed": True,
                    "last_call_returned_true": True,
                }
                for phase in (
                    "first_reset_task_setup",
                    "official_evaluator_postconfig",
                    "second_reset_task_setup",
                )
            },
        },
        "evaluator_probe": {
            "official_evaluator_executed": True,
            "infeasible": False,
            "metric_applicability": "case_specific_gold_metric",
            "action_history_empty_before": True,
            "action_history_empty_after": True,
            "score": 0.0,
            "score_raw_type": "float",
            "score_numeric_finite": True,
            "result_getter_executed": True,
            "expected_getter_executed": True,
            "gold_metric_executed": True,
            "evaluator_func": "check_include_exclude",
            "task_evaluator_sha256": task_evaluator_sha256,
            "expected_getter_required_indices": [0],
            "all_trace_records_completed": True,
            "metric_getter_index_pairs_valid": True,
            "dispatch_trace_valid": True,
            "bound_dispatch": {
                "result_getter_bindings": [{
                    "index": 0, "path": "desktop_env.evaluators.getters.file.get_vm_file",
                }],
                "expected_getter_bindings": [{
                    "index": 0, "path": "desktop_env.evaluators.getters.file.get_rule",
                }],
                "metric_bindings": [{
                    "index": 0, "path": "desktop_env.evaluators.metrics.general.check_include_exclude",
                }],
            },
            "execution_trace": [
                {
                    "kind": "result_getter", "index": 0,
                    "path": "desktop_env.evaluators.getters.file.get_vm_file",
                    "entered": True, "completed": True,
                },
                {
                    "kind": "expected_getter", "index": 0,
                    "path": "desktop_env.evaluators.getters.file.get_rule",
                    "entered": True, "completed": True,
                },
                {
                    "kind": "metric", "index": 0,
                    "path": "desktop_env.evaluators.metrics.general.check_include_exclude",
                    "entered": True, "completed": True,
                },
            ],
        },
        "wait_probe": {
            "action": "WAIT", "reward": 0.0, "done": False, "info": {},
            "environment_used_after_wait": True,
            "action_history_before": [], "action_history_after": ["WAIT"],
        },
        "reset_probe": {
            "provider": "docker",
            "first_observation_sha256": "a" * 64,
            "second_observation_sha256": "b" * 64,
            "observation_equality_required": False,
            "first_container_id": "1" * 64,
            "second_container_id": "2" * 64,
            "container_replaced": True,
            "action_history_cleared": True,
            "second_reset_completed": True,
            "lifecycle_phase_order": [
                "first_reset", "official_evaluator", "wait", "second_reset",
            ],
        },
    }
    entry["evidence_sha256"] = canonical_digest(entry)
    return entry


def marble_smoke():
    def digest(value):
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    previous = "0" * 64
    audit = []
    for index, event in enumerate((
        "control_plane_started", "environment_reset",
        "healthcheck_transcript_appended", "environment_reset",
    )):
        body = {"event": event, "state_sha256": str(index + 1) * 64, "previous_sha256": previous}
        body["record_sha256"] = digest(body)
        previous = body["record_sha256"]
        audit.append(body)
    entry = {
        "schema_version": "source-native-marble-environment-smoke-v1",
        "case_id": "m1",
        "benchmark": "MultiAgentBench",
        "source_task_id": "database:001",
        "scenario": "database",
        "status": ENVIRONMENT_SMOKE_READY_STATUS,
        "execution_scope": INFRASTRUCTURE_SMOKE_SCOPE,
        "qualification_profile": MARBLE_SMOKE_PROFILE,
        "adapter": "LocalMarbleEnvironment",
        "upstream_engine_executed": False,
        "checks": {name: True for name in (
            "official_source_record_bound", "source_record_hash_verified",
            "hydrated_config_loaded", "config_entrypoint_resolved",
            "engine_entrypoint_resolved", "environment_entrypoint_resolved",
            "evaluator_entrypoint_resolved", "scenario_evaluator_bound",
            "offline_provider_healthcheck", "zero_external_model_calls",
            "local_control_plane_started", "environment_reset_reproducible",
            "native_healthcheck_transcript_appended", "native_state_digest_changed",
            "control_plane_audit_chain_valid",
        )},
        "bindings": {
            "config": "marble.configs.config.Config",
            "engine": "marble.engine.engine.Engine",
            "environment": "marble.environments.db_env.DBEnvironment",
            "evaluator": "marble.evaluator.evaluator.Evaluator",
            "evaluator_method": "evaluate_task_db",
        },
        "environment": {
            "scenario": "database", "type": "DB",
            "external_service": "docker-compose-postgres-prometheus",
        },
        "source_evidence": {
            "jsonl_path": "upstream/marble/database.jsonl", "line_number": 1,
            "record_sha256": "a" * 64, "official_task_sha256": "b" * 64,
            "native_config_sha256": "c" * 64, "native_case_sha256": "d" * 64,
        },
        "provider_probe": {
            "provider": "offline/deterministic-healthcheck", "network_calls": 0,
            "request_sha256": "e" * 64, "response_sha256": "f" * 64,
        },
        "control_plane": {
            "adapter": "LocalMarbleEnvironment", "upstream_engine_executed": False,
            "started_state_sha256": "1" * 64, "baseline_state_sha256": "2" * 64,
            "checkpoint_state_sha256": "3" * 64, "reset_state_sha256": "2" * 64,
            "transcript_event": {
                "kind": "environment_healthcheck", "actor_kind": "infrastructure_control_plane",
                "task_action": False, "sequence": 1, "logical_clock": 1,
                "provenance": {"execution_scope": INFRASTRUCTURE_SMOKE_SCOPE},
            },
            "audit": audit,
        },
        "claims": {
            "model_episode_executed": False, "gold_evaluator_executed": False,
            "task_scored": False, "formal_promotion_ready": False,
        },
        "real_episode_launcher": {"command": ["python", "run.py"], "preflight": "fail_closed"},
    }
    entry["evidence_sha256"] = digest(entry)
    return entry


def test_unknown_environment_smoke_profile_is_fail_closed():
    entry = smoke()
    entry["qualification_profile"] = "unknown"
    assert qualification(entry, benchmark="OSWorld", source_task_id="source-1") == (
        False,
        "case_runtime_validation_incomplete",
    )


def test_marble_environment_smoke_profile_is_strict_and_not_a_model_episode():
    entry = marble_smoke()
    assert environment_smoke_qualification(
        entry, benchmark="MultiAgentBench", source_task_id="database:001"
    ) == (True, None)
    assert qualification(
        entry, benchmark="MultiAgentBench", source_task_id="database:001"
    ) == (False, "environment_smoke_only_not_native_runtime")
    entry["claims"]["model_episode_executed"] = True
    assert environment_smoke_qualification(
        entry, benchmark="MultiAgentBench", source_task_id="database:001"
    ) == (False, "case_environment_smoke_validation_incomplete")


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("provider_probe", "network_calls", 1),
        ("bindings", "evaluator_method", "wrong"),
        ("source_evidence", "record_sha256", "not-a-digest"),
        ("environment", "external_service", None),
    ],
)
def test_marble_environment_smoke_rejects_incomplete_evidence(section, field, value):
    entry = marble_smoke()
    entry[section][field] = value
    assert environment_smoke_qualification(
        entry, benchmark="MultiAgentBench", source_task_id="database:001"
    ) == (False, "case_environment_smoke_validation_incomplete")


def test_infrastructure_smoke_never_counts_as_model_execution():
    rows, report, summary = synchronize_runtime_metadata(
        [manifest_row()], {"spec_ready_count": 1, "runtime_executed_count": 99}, {"c1": smoke()}
    )
    assert rows[0]["runtime_ready"] is False
    assert rows[0]["runtime_blocker"] == "environment_smoke_only_not_native_runtime"
    assert rows[0]["preserved"] == {"field": True}
    assert report["environment_smoke_ready_benchmark_counts"] == {"OSWorld": 1}
    assert report["runtime_ready_benchmark_counts"] == {}
    assert report["runtime_registry_status_counts"] == {ENVIRONMENT_SMOKE_READY_STATUS: 1}
    assert report["runtime_execution_scope_counts"] == {INFRASTRUCTURE_SMOKE_SCOPE: 1}
    assert summary["runtime_executed_count"] == 0


def test_marble_initialization_is_counted_but_never_runtime_ready(monkeypatch):
    from async_rbench import marble_runtime

    entry = {
        "case_id": "m1",
        "benchmark": "MultiAgentBench",
        "source_task_id": "coding:001",
        "status": NATIVE_ENVIRONMENT_INITIALIZATION_STATUS,
        "execution_scope": NATIVE_RUNTIME_SCOPE,
        "qualification_profile": MARBLE_NATIVE_INITIALIZATION_PROFILE,
    }
    monkeypatch.setattr(
        marble_runtime,
        "validate_native_environment_evidence",
        lambda candidate: (candidate is entry, None),
    )

    assert native_environment_initialization_qualification(
        entry, benchmark="MultiAgentBench", source_task_id="coding:001"
    ) == (True, None)
    assert qualification(
        entry, benchmark="MultiAgentBench", source_task_id="coding:001"
    ) == (False, "native_environment_initialization_only_not_runtime_ready")

    rows, report, summary = synchronize_runtime_metadata(
        [manifest_row("m1", "MultiAgentBench", "coding:001")],
        {"spec_ready_count": 1},
        {"m1": entry},
    )
    assert rows[0]["runtime_ready"] is False
    assert report["native_environment_initialization_benchmark_counts"] == {
        "MultiAgentBench": 1
    }
    assert report["runtime_ready_benchmark_counts"] == {}
    assert summary["runtime_executed_count"] == 0


def test_self_reported_model_evidence_without_root_never_counts():
    entry = smoke()
    entry["model_execution"] = {
        "status": "executed",
        "execution_scope": MODEL_EPISODE_SCOPE,
        "episode_id": "episode-1",
        "model_id": "model-1",
        "mode": "linear",
        "evidence": {
            "path": "episodes/episode-1.json",
            "sha256": "a" * 64,
            "path_exists": True,
            "sha256_verified": True,
        },
    }
    _, report, _ = synchronize_runtime_metadata(
        [manifest_row()], {"spec_ready_count": 1}, {"c1": entry}
    )
    assert report["runtime_executed_count"] == 0
    assert report["runtime_executed_benchmark_counts"] == {}
    del entry["model_execution"]["model_id"]
    _, report, _ = synchronize_runtime_metadata(
        [manifest_row()], {"spec_ready_count": 1}, {"c1": entry}
    )
    assert report["runtime_executed_count"] == 0


def test_model_episode_can_be_verified_against_real_evidence_file(tmp_path):
    evidence_dir = tmp_path / "episodes"
    evidence_dir.mkdir()
    evidence_path = evidence_dir / "episode.json"
    evidence_path.write_text('{"result":"ok"}\n', encoding="utf-8")
    digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    entry = smoke()
    entry["model_execution"] = {
        "status": "executed",
        "execution_scope": MODEL_EPISODE_SCOPE,
        "episode_id": "episode-1",
        "model_id": "model-1",
        "mode": "linear",
        "evidence": {
            "path": "episodes/episode.json",
            "sha256": digest,
            "path_exists": True,
            "sha256_verified": True,
        },
    }
    assert model_execution_validated(entry, evidence_root=tmp_path) is True
    entry["model_execution"]["evidence"]["path"] = str(evidence_path.resolve())
    assert model_execution_validated(entry, evidence_root=tmp_path) is False
    entry["model_execution"]["evidence"]["path"] = "episodes/episode.json"
    _, report, _ = synchronize_runtime_metadata(
        [manifest_row()],
        {"spec_ready_count": 1},
        {"c1": entry},
        model_evidence_root=tmp_path,
    )
    assert report["runtime_executed_count"] == 1
    entry["model_execution"]["evidence"]["path_exists"] = False
    assert model_execution_validated(entry, evidence_root=tmp_path) is False
    entry["model_execution"]["evidence"]["path_exists"] = True
    entry["model_execution"]["evidence"]["sha256"] = "0" * 64
    assert model_execution_validated(entry, evidence_root=tmp_path) is False


def test_smoke_merge_cannot_downgrade_native_or_drop_model_evidence():
    native = {
        "case_id": "c1", "benchmark": "OSWorld", "source_task_id": "source-1",
        "status": NATIVE_RUNTIME_READY_STATUS, "execution_scope": NATIVE_RUNTIME_SCOPE,
        "qualification_profile": "real-osworld-v1",
        "model_execution": {"episode_id": "preserved"},
    }
    merged = merge_registry_entries(native, smoke())
    assert merged["status"] == NATIVE_RUNTIME_READY_STATUS
    assert merged["model_execution"] == {"episode_id": "preserved"}
    assert merged["environment_smoke"]["status"] == ENVIRONMENT_SMOKE_READY_STATUS
    assert environment_smoke_qualification(
        merged, benchmark="OSWorld", source_task_id="source-1"
    ) == (True, None)


def test_builtin_osworld_native_profile_is_available_in_a_fresh_process():
    assert qualification(
        osworld_native(), benchmark="OSWorld", source_task_id="source-1"
    ) == (True, None)


def test_osworld_native_profile_remains_valid_when_registry_preserves_smoke_nested():
    merged = merge_registry_entries(smoke(), osworld_native())
    assert merged["environment_smoke"]["status"] == ENVIRONMENT_SMOKE_READY_STATUS
    assert qualification(
        merged, benchmark="OSWorld", source_task_id="source-1"
    ) == (True, None)


def test_builtin_osworld_native_profile_rejects_untraced_metric_or_reused_container():
    entry = osworld_native()
    entry["evaluator_probe"]["execution_trace"] = []
    entry["evidence_sha256"] = canonical_digest(
        {key: value for key, value in entry.items() if key != "evidence_sha256"}
    )
    assert qualification(
        entry, benchmark="OSWorld", source_task_id="source-1"
    ) == (False, "case_runtime_validation_incomplete")


def test_builtin_osworld_native_profile_rejects_failed_trace_missing_expected_and_weak_wait():
    def assert_invalid(entry):
        entry["evidence_sha256"] = canonical_digest(
            {key: value for key, value in entry.items() if key != "evidence_sha256"}
        )
        assert qualification(
            entry, benchmark="OSWorld", source_task_id="source-1"
        ) == (False, "case_runtime_validation_incomplete")

    entry = osworld_native()
    entry["evaluator_probe"]["execution_trace"].append({
        "kind": "result_getter", "index": 0,
        "path": "desktop_env.evaluators.getters.file.get_vm_file",
        "entered": True, "completed": False, "exception_type": "FileNotFoundError",
    })
    assert_invalid(entry)

    entry = osworld_native()
    entry["provider_preflight"]["details"]["python_environment_isolated"] = False
    assert_invalid(entry)

    entry = osworld_native()
    entry["evaluator_probe"]["execution_trace"] = [
        record for record in entry["evaluator_probe"]["execution_trace"]
        if record["kind"] != "expected_getter"
    ]
    assert_invalid(entry)

    entry = osworld_native()
    entry["wait_probe"]["reward"] = float("nan")
    entry["wait_probe"]["info"] = {"fail": True}
    assert_invalid(entry)

    entry = osworld_native()
    entry["setup_probe"]["calls"][-1]["returned_true"] = False
    entry["setup_probe"]["phase_results"]["second_reset_task_setup"][
        "last_call_returned_true"
    ] = False
    assert_invalid(entry)


def test_builtin_osworld_native_profile_rejects_infeasible_score_one_and_bool_score():
    def resign(entry):
        entry["evidence_sha256"] = canonical_digest(
            {key: value for key, value in entry.items() if key != "evidence_sha256"}
        )
        return entry

    entry = osworld_native()
    evaluator = entry["evaluator_probe"]
    evaluator.update({
        "infeasible": True,
        "metric_applicability": "not_applicable_infeasible",
        "evaluator_func": "infeasible",
        "score": 1.0,
        "result_getter_executed": False,
        "expected_getter_executed": False,
        "gold_metric_executed": False,
        "expected_getter_required_indices": [],
        "execution_trace": [],
    })
    entry["official_gold_metric_executed"] = False
    entry["checks"]["case_specific_result_getter_executed"] = False
    entry["checks"]["case_specific_gold_metric_executed"] = False
    assert qualification(
        resign(entry), benchmark="OSWorld", source_task_id="source-1"
    ) == (False, "case_runtime_validation_incomplete")

    entry = osworld_native()
    entry["evaluator_probe"]["score"] = True
    entry["evaluator_probe"]["score_raw_type"] = "bool"
    assert qualification(
        resign(entry), benchmark="OSWorld", source_task_id="source-1"
    ) == (False, "case_runtime_validation_incomplete")


def test_builtin_osworld_native_profile_allows_attested_tcg_fallback():
    entry = osworld_native()
    entry["kvm_probe"].update({"device_available": False, "exit_code": 1})
    entry["runtime_compatibility_adapter"].update({
        "enabled": False,
        "kvm_exists_overridden": False,
        "provider_module_os_replaced": False,
        "acceleration_mode": "tcg",
    })
    entry["evidence_sha256"] = canonical_digest(
        {key: value for key, value in entry.items() if key != "evidence_sha256"}
    )
    assert qualification(
        entry, benchmark="OSWorld", source_task_id="source-1"
    ) == (True, None)

    entry = osworld_native()
    entry["reset_probe"]["second_container_id"] = entry["reset_probe"]["first_container_id"]
    entry["evidence_sha256"] = canonical_digest(
        {key: value for key, value in entry.items() if key != "evidence_sha256"}
    )
    assert qualification(
        entry, benchmark="OSWorld", source_task_id="source-1"
    ) == (False, "case_runtime_validation_incomplete")


def test_osworld_native_batch_resume_revalidates_source_assets_and_vm_path(tmp_path):
    attestation = tmp_path / "asset_attestation.json"
    attestation.write_text("{}\n", encoding="utf-8")
    bootstrap_report = tmp_path / "osworld-native-bootstrap-report.json"
    bootstrap_report.write_text("{}\n", encoding="utf-8")
    environment_lock = tmp_path / "osworld-native-requirements.lock"
    environment_lock.write_text("package==1\n", encoding="utf-8")
    vm_path = tmp_path / "Ubuntu.qcow2"
    vm_path.write_bytes(b"test")
    entry = osworld_native()
    entry["provider_preflight"]["details"]["asset_attestation_sha256"] = hashlib.sha256(
        attestation.read_bytes()
    ).hexdigest()
    entry["provider_preflight"]["details"]["python_bootstrap_report_sha256"] = (
        hashlib.sha256(bootstrap_report.read_bytes()).hexdigest()
    )
    entry["provider_preflight"]["details"]["python_environment_lock_sha256"] = (
        hashlib.sha256(environment_lock.read_bytes()).hexdigest()
    )
    entry["provider_preflight"]["details"]["vm_disk_path"] = str(vm_path.resolve())
    source_hashes = {
        "factory_sha256": "a" * 64,
        "provider_source_sha256": "b" * 64,
        "manager_source_sha256": "c" * 64,
    }
    entry["provider_preflight"]["details"].update(source_hashes)
    entry["evidence_sha256"] = canonical_digest(
        {key: value for key, value in entry.items() if key != "evidence_sha256"}
    )
    case = SimpleNamespace(
        case_id="c1",
        source_task_id="source-1",
        config_sha256="3" * 64,
        dispatch=SimpleNamespace(evaluator_sha256="4" * 64),
        task={"config": [], "evaluator": {"func": "check_include_exclude"}},
        upstream_revision="d" * 40,
    )
    current_provider_details = dict(source_hashes)
    upstream_git_binding = {
        "probe_succeeded": True,
        "tracked_tree_clean": True,
        "revision": case.upstream_revision,
    }
    assert reusable_evidence(
        entry,
        case,
        attestation_path=attestation,
        vm_path=vm_path.resolve(),
        bootstrap_report_path=bootstrap_report,
        environment_lock_path=environment_lock,
        current_provider_details=current_provider_details,
        upstream_git_binding=upstream_git_binding,
    ) is True
    matcher_kwargs = {
        "attestation_path": attestation,
        "vm_path": vm_path.resolve(),
        "bootstrap_report_path": bootstrap_report,
        "environment_lock_path": environment_lock,
        "current_provider_details": current_provider_details,
        "upstream_git_binding": upstream_git_binding,
    }
    cloned = copy.deepcopy(entry)
    cloned["case_id"] = "different-case"
    assert evidence_matches_current_case(cloned, case, **matcher_kwargs) is False
    evaluator_drift = copy.deepcopy(entry)
    evaluator_drift["evaluator_probe"]["evaluator_func"] = "different"
    assert evidence_matches_current_case(evaluator_drift, case, **matcher_kwargs) is False
    setup_drift = copy.deepcopy(entry)
    setup_drift["setup_probe"]["calls"][0]["config_sha256"] = "0" * 64
    assert evidence_matches_current_case(setup_drift, case, **matcher_kwargs) is False
    provider_drift = dict(current_provider_details)
    provider_drift["manager_source_sha256"] = "e" * 64
    assert evidence_matches_current_case(
        entry, case, **{**matcher_kwargs, "current_provider_details": provider_drift}
    ) is False
    assert evidence_matches_current_case(
        entry,
        case,
        **{
            **matcher_kwargs,
            "upstream_git_binding": {
                **upstream_git_binding,
                "tracked_tree_clean": False,
            },
        },
    ) is False
    corrupt = copy.deepcopy(entry)
    corrupt["checks"] = "corrupt-nested-object"
    corrupt["evidence_sha256"] = canonical_digest(
        {key: value for key, value in corrupt.items() if key != "evidence_sha256"}
    )
    assert qualify_entry_safely(
        corrupt,
        source_task_id=case.source_task_id,
    ) == (False, "native_case_evidence_validation_error:AttributeError")
    assert reusable_evidence(
        corrupt,
        case,
        attestation_path=attestation,
        vm_path=vm_path.resolve(),
        bootstrap_report_path=bootstrap_report,
        environment_lock_path=environment_lock,
        current_provider_details=current_provider_details,
        upstream_git_binding=upstream_git_binding,
    ) is False
    vm_path.unlink()
    assert reusable_evidence(
        entry,
        case,
        attestation_path=attestation,
        vm_path=vm_path.resolve(),
        bootstrap_report_path=bootstrap_report,
        environment_lock_path=environment_lock,
        current_provider_details=current_provider_details,
        upstream_git_binding=upstream_git_binding,
    ) is False
    vm_path.write_bytes(b"test")
    case.config_sha256 = "9" * 64
    assert reusable_evidence(
        entry,
        case,
        attestation_path=attestation,
        vm_path=vm_path.resolve(),
        bootstrap_report_path=bootstrap_report,
        environment_lock_path=environment_lock,
        current_provider_details=current_provider_details,
        upstream_git_binding=upstream_git_binding,
    ) is False


@pytest.mark.parametrize("unavailable", ["daemon_reachable", "docker_digest_image_present"])
def test_osworld_native_batch_live_resume_preflight_rejects_daemon_or_image_loss(
    unavailable,
):
    details = {
        "daemon_reachable": True,
        "docker_image_present": True,
        "docker_digest_image_present": True,
        "docker_latest_image_present": True,
        "vm_disk_present": True,
        "asset_attestation_verified": True,
        "python_bootstrap_verified": True,
    }
    provider_probe = SimpleNamespace(
        provider="docker",
        configuration_resolved=True,
        launch_ready=True,
        blockers=(),
        details=details,
    )
    kvm_probe = {"attempted": True, "device_available": True, "exit_code": 0}
    assert live_provider_preflight_valid(provider_probe, kvm_probe) is True

    details[unavailable] = False
    assert live_provider_preflight_valid(provider_probe, kvm_probe) is False


def test_osworld_native_batch_timeout_never_claims_or_removes_concurrent_container(
    tmp_path,
):
    preexisting = "1" * 64
    owned = "2" * 64
    before = {
        "probe_succeeded": True,
        "official_container_ids": [preexisting],
        "provider_container_ids": [preexisting],
    }
    probes = iter([
        {
            "probe_succeeded": True,
            "official_container_ids": [preexisting, owned],
            "provider_container_ids": [preexisting, owned],
        }
    ])

    def inspect(_vm_path):
        return next(probes)

    cleanup = cleanup_timeout_provider_containers(
        before,
        tmp_path / "Ubuntu.qcow2",
        inspect_fn=inspect,
    )
    assert cleanup["passed"] is False
    assert cleanup["ownership_proven"] is False
    assert cleanup["destructive_cleanup_permitted"] is False
    assert cleanup["cleanup_attempted"] is False
    assert cleanup["suspected_new_provider_container_ids"] == [owned]
    assert cleanup["manual_cleanup_required"] is True


def test_osworld_native_batch_postflight_rejects_residual_desktop_container():
    provider_probe = SimpleNamespace(
        provider="docker",
        configuration_resolved=True,
        launch_ready=True,
        blockers=(),
        details={
            "daemon_reachable": True,
            "docker_image_present": True,
            "docker_digest_image_present": True,
            "docker_latest_image_present": True,
            "vm_disk_present": True,
            "asset_attestation_verified": True,
            "python_bootstrap_verified": True,
        },
    )
    kvm_probe = {"attempted": True, "device_available": False, "exit_code": 1}
    clean = {
        "probe_succeeded": True,
        "official_container_ids": [],
        "provider_container_ids": [],
    }
    assert live_provider_postflight_valid(provider_probe, kvm_probe, clean) is True

    residual = copy.deepcopy(clean)
    residual["official_container_ids"] = ["3" * 64]
    assert live_provider_postflight_valid(provider_probe, kvm_probe, residual) is False


def test_osworld_docker_bind_source_matching_is_exact_across_windows_dialects():
    # Synthetic drive root (not the author's real checkout) so the dialect
    # mapping (X:/ -> /host_mnt/x/, /run/desktop/mnt/host/x/) is tested
    # independently of any machine's private path.
    vm_path = Path("F:/dtbench-fixture/artifacts/native-runtime-v4/osworld-assets/Ubuntu.qcow2")
    assert docker_bind_source_matches_file(str(vm_path.resolve()), vm_path) is True
    assert docker_bind_source_matches_file(
        "/run/desktop/mnt/host/f/dtbench-fixture/artifacts/native-runtime-v4/"
        "osworld-assets/Ubuntu.qcow2",
        vm_path,
    ) is True
    assert docker_bind_source_matches_file(
        "/host_mnt/f/dtbench-fixture/artifacts/native-runtime-v4/"
        "osworld-assets/Ubuntu.qcow2",
        vm_path,
    ) is True
    assert docker_bind_source_matches_file(str(vm_path.parent), vm_path) is False
    assert docker_bind_source_matches_file(
        "F:/different/Ubuntu.qcow2", vm_path
    ) is False


def _docker_identity(identifier="daemon-1"):
    return {
        "id": identifier,
        "name": "desktop-linux",
        "server_version": "27.0",
        "docker_root_dir": "/var/lib/docker",
        "os_type": "linux",
        "architecture": "x86_64",
    }


def _cli_sdk_probes(*, context="desktop-linux", base_url="npipe://desktop"):
    identity = _docker_identity()
    cli = {
        "probe_succeeded": True,
        "context": context,
        "daemon_identity": copy.deepcopy(identity),
    }
    sdk = {
        "probe_succeeded": True,
        "client_base_url": base_url,
        "daemon_identity": copy.deepcopy(identity),
        "image_identities": {"digest": "image", "latest": "image", "untagged": "image"},
    }
    return cli, sdk


def test_osworld_batch_rejects_cli_sdk_or_cross_phase_docker_identity_drift():
    pre_cli, pre_sdk = _cli_sdk_probes()
    post_cli, post_sdk = copy.deepcopy(pre_cli), copy.deepcopy(pre_sdk)
    assert docker_cli_sdk_daemon_match(pre_cli, pre_sdk) is True
    assert docker_provider_identity_stable(
        pre_cli, pre_sdk, post_cli, post_sdk
    ) is True

    mismatched_sdk = copy.deepcopy(pre_sdk)
    mismatched_sdk["daemon_identity"]["id"] = "other"
    assert docker_cli_sdk_daemon_match(pre_cli, mismatched_sdk) is False
    changed_context = copy.deepcopy(post_cli)
    changed_context["context"] = "default"
    assert docker_provider_identity_stable(
        pre_cli, pre_sdk, changed_context, post_sdk
    ) is False
    changed_base_url = copy.deepcopy(post_sdk)
    changed_base_url["client_base_url"] = "tcp://other"
    assert docker_provider_identity_stable(
        pre_cli, pre_sdk, post_cli, changed_base_url
    ) is False


def test_osworld_sdk_provider_probe_uses_exact_read_only_file_bind_and_tcg(tmp_path):
    vm_path = tmp_path / "Ubuntu.qcow2"
    vm_path.write_bytes(b"qcow")
    created = {}

    class Image:
        id = OFFICIAL_OSWORLD_DOCKER_IMAGE_ID

    class Images:
        def get(self, _reference):
            return Image()

    class Container:
        id = "probe-container"

        def __init__(self):
            self.attrs = {
                "Mounts": [{
                    "Type": "bind",
                    "Source": str(vm_path.resolve()),
                    "Destination": "/System.qcow2",
                    "RW": False,
                }]
            }

        def reload(self):
            return None

        def start(self):
            return None

        def wait(self, timeout):
            assert timeout == 60
            return {"StatusCode": 0}

        def logs(self, **_kwargs):
            return b""

        def remove(self, **_kwargs):
            return None

    container = Container()

    class Containers:
        def create(self, _image, **kwargs):
            created.update(kwargs)
            return container

        def list(self, **_kwargs):
            return []

    class Client:
        api = SimpleNamespace(base_url="npipe://desktop")
        images = Images()
        containers = Containers()

        def ping(self):
            return True

        def info(self):
            return {
                "ID": "daemon-1", "Name": "desktop-linux", "ServerVersion": "27.0",
                "DockerRootDir": "/var/lib/docker", "OSType": "linux",
                "Architecture": "x86_64",
            }

        def close(self):
            return None

    result = probe_docker_sdk_provider(
        vm_path, kvm_available=False, client_factory=Client
    )
    assert result["probe_succeeded"] is True
    assert created["volumes"] == {
        str(vm_path.resolve()): {"bind": "/System.qcow2", "mode": "ro"}
    }
    assert created["devices"] == []
    assert created["environment"] == {"KVM": "N"}
    assert created["command"][1] == 'test -s /System.qcow2 && test "$KVM" = N'

    container.attrs["Mounts"][0]["Source"] = str(vm_path.parent)
    expanded = probe_docker_sdk_provider(
        vm_path, kvm_available=False, client_factory=Client
    )
    assert expanded["probe_succeeded"] is False
    assert expanded["checks"]["exact_vm_file_bind_read_only"] is False

    def failed_remove(**_kwargs):
        raise RuntimeError("remove failed")

    container.attrs["Mounts"][0]["Source"] = str(vm_path.resolve())
    container.remove = failed_remove
    cleanup_failed = probe_docker_sdk_provider(
        vm_path, kvm_available=False, client_factory=Client
    )
    assert cleanup_failed["probe_succeeded"] is False
    assert cleanup_failed["checks"]["minimal_container_cleanup_succeeded"] is False


def test_osworld_batch_retry_classifier_and_intercase_probe_fail_closed():
    clean = {
        "lock_acquired": True,
        "probe_succeeded": True,
        "official_container_ids": [],
        "provider_container_ids": [],
    }
    assert provider_containers_absent(clean) is True
    assert provider_containers_absent({**clean, "official_container_ids": ["x"]}) is False
    assert infrastructure_failure_retryable(
        None, return_code=2, process_failure=None
    ) is True
    assert infrastructure_failure_retryable(
        {"failure": {"type": "TimeoutError"}},
        return_code=1,
        process_failure=None,
    ) is True
    assert infrastructure_failure_retryable(
        {"failure": {"type": "AssertionError"}},
        return_code=1,
        process_failure=None,
    ) is False


def test_batch_json_atomic_replace_failure_preserves_old_and_concurrent_writes_are_valid(
    tmp_path, monkeypatch
):
    target = tmp_path / "batch_report.json"
    target.write_text('{"old":true}\n', encoding="utf-8")
    original = target.read_bytes()

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr("scripts.run_osworld_native_batch.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        write_batch_json(target, {"new": True})
    assert target.read_bytes() == original
    assert list(tmp_path.glob(".batch_report.json.*.tmp")) == []
    monkeypatch.undo()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda value: write_batch_json(target, {"value": value}), range(20)))
    assert json.loads(target.read_text(encoding="utf-8"))["value"] in range(20)
    assert list(tmp_path.glob(".batch_report.json.*.tmp")) == []


def test_osworld_native_batch_rejects_direct_registry_merge_option():
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "run_osworld_native_batch.py"),
            "--case-id", "c1", "--merge-registry",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: --merge-registry" in result.stderr


def test_gold_evidence_outranks_native_and_preserves_it_nested():
    gold = {
        "case_id": "c1", "benchmark": "OSWorld", "source_task_id": "source-1",
        "status": READY_STATUS, "gold_report": {"sha256": "g" * 64},
    }
    merged = merge_registry_entries(osworld_native(), gold)
    assert merged["status"] == READY_STATUS
    assert merged["gold_report"] == {"sha256": "g" * 64}
    assert merged["native_environment"]["status"] == NATIVE_RUNTIME_READY_STATUS


def test_native_runtime_profile_registration_is_fail_closed():
    profile = "test-native-profile"
    entry = {
        "case_id": "c1", "benchmark": "OSWorld", "source_task_id": "source-1",
        "status": NATIVE_RUNTIME_READY_STATUS, "execution_scope": NATIVE_RUNTIME_SCOPE,
        "qualification_profile": profile, "real_environment_health": True,
    }
    assert qualification(entry, benchmark="OSWorld", source_task_id="source-1") == (
        False, "case_runtime_validation_incomplete"
    )
    register_native_runtime_profile(profile, lambda value: value.get("real_environment_health") is True)
    try:
        assert qualification(entry, benchmark="OSWorld", source_task_id="source-1") == (True, None)
    finally:
        NATIVE_RUNTIME_PROFILE_VALIDATORS.pop(profile)


@pytest.mark.parametrize("field", ["benchmark", "source_task_id"])
def test_sync_rejects_registry_identity_mismatch(field):
    entry = smoke()
    entry[field] = "wrong"
    with pytest.raises(ValueError, match="mismatch"):
        synchronize_runtime_metadata([manifest_row()], {"spec_ready_count": 1}, {"c1": entry})


def test_sync_rejects_registry_case_outside_manifest():
    with pytest.raises(ValueError, match="outside manifest"):
        synchronize_runtime_metadata([manifest_row()], {"spec_ready_count": 1}, {"other": smoke("other")})


def test_atomic_replace_writes_both_validated_payloads():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        manifest_path = root / "native_manifest.jsonl"
        report_path = root / "production_report.json"
        manifest_path.write_text("old manifest\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
        rows, report, _ = synchronize_runtime_metadata(
            [manifest_row()], {"spec_ready_count": 1}, {"c1": smoke()}
        )
        manifest_bytes, report_bytes = serialize_runtime_metadata(rows, report)
        replace_runtime_metadata_atomically(manifest_path, report_path, manifest_bytes, report_bytes)
        assert json.loads(manifest_path.read_text(encoding="utf-8"))["runtime_ready"] is False
        assert json.loads(report_path.read_text(encoding="utf-8"))["runtime_executed_count"] == 0


def test_sync_cli_updates_three_artifacts_then_rejects_bad_merge_without_writes(tmp_path):
    source_root = tmp_path / "source-native-v4"
    source_root.mkdir()
    manifest_path = source_root / "native_manifest.jsonl"
    report_path = source_root / "production_report.json"
    registry_path = tmp_path / "native-runtime-v4" / "runtime_registry.jsonl"
    registry_path.parent.mkdir()
    evidence_path = tmp_path / "smoke.json"
    manifest_path.write_text(
        json.dumps(manifest_row(), sort_keys=True) + "\n", encoding="utf-8"
    )
    report_path.write_text('{"spec_ready_count":1}\n', encoding="utf-8")
    registry_path.write_bytes(b"")
    evidence_path.write_text(json.dumps(smoke()), encoding="utf-8")
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts" / "sync_source_native_runtime.py"),
        "--root",
        str(source_root),
        "--runtime-registry",
        str(registry_path),
        "--merge-evidence",
        str(evidence_path),
    ]

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["runtime_blocker"] == (
        "environment_smoke_only_not_native_runtime"
    )
    assert json.loads(report_path.read_text(encoding="utf-8"))[
        "environment_smoke_ready_count"
    ] == 1
    assert json.loads(registry_path.read_text(encoding="utf-8"))["status"] == (
        ENVIRONMENT_SMOKE_READY_STATUS
    )

    before = {
        path: path.read_bytes() for path in (registry_path, manifest_path, report_path)
    }
    invalid = smoke()
    invalid["source_task_id"] = "wrong-source"
    evidence_path.write_text(json.dumps(invalid), encoding="utf-8")
    rejected = subprocess.run(command, capture_output=True, text=True, check=False)
    assert rejected.returncode != 0
    assert "identity mismatch" in rejected.stdout
    assert {
        path: path.read_bytes() for path in (registry_path, manifest_path, report_path)
    } == before
