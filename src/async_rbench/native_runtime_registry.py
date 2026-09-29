"""Per-case runtime qualification for source-native benchmark cases.

Static source binding and a running Docker daemon are necessary but not
sufficient.  A case becomes runtime-ready only after its immutable image,
gold evaluator, and stateful checkpoint mechanism have all been exercised.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable


READY_STATUS = "gold_and_checkpoint_validated"
ENVIRONMENT_SMOKE_READY_STATUS = "environment_smoke_validated"
NATIVE_RUNTIME_READY_STATUS = "native_environment_validated"
NATIVE_ENVIRONMENT_INITIALIZATION_STATUS = "native_environment_initialization_validated"
OSWORLD_SMOKE_PROFILE = "osworld_local_control_plane_v1"
MARBLE_SMOKE_PROFILE = "marble_environment_smoke_v1"
OSWORLD_NATIVE_PROFILE = "osworld_native_environment_v2"
MARBLE_NATIVE_INITIALIZATION_PROFILE = "marble_native_environment_initialization_v1"
INFRASTRUCTURE_SMOKE_SCOPE = "infrastructure_smoke"
NATIVE_RUNTIME_SCOPE = "native_runtime"
MODEL_EPISODE_SCOPE = "model_episode"
MODEL_EXECUTION_STATUS = "executed"
MODEL_EXECUTION_MODES = frozenset({"react", "linear", "async"})
RUNTIME_REPORT_FIELDS = (
    "environment_smoke_ready_count",
    "environment_smoke_ready_benchmark_counts",
    "native_environment_initialization_count",
    "native_environment_initialization_benchmark_counts",
    "runtime_ready_count",
    "runtime_ready_benchmark_counts",
    "runtime_blocker_counts",
    "runtime_registry_status_counts",
    "runtime_execution_scope_counts",
    "runtime_executed_count",
    "runtime_executed_benchmark_counts",
)

_LEGACY_INFRASTRUCTURE_CHECKS = frozenset({
    "immutable_environment_bound",
    "gold_evaluator_resolved",
    "native_reproduction_executed",
    "native_checkpoint_changed_state",
    "audit_chain_valid",
})
_SHA256_HEX = frozenset("0123456789abcdef")

_MARBLE_BINDINGS = {
    "bargaining": {
        "environment": "marble.environments.world_env.WorldSimulationEnvironment",
        "evaluator_method": "evaluate_task_world",
        "environment_type": "WorldSimulation",
        "external_service": None,
    },
    "coding": {
        "environment": "marble.environments.coding_env.CodingEnvironment",
        "evaluator_method": "evaluate_code_quality",
        "environment_type": "Coding",
        "external_service": None,
    },
    "database": {
        "environment": "marble.environments.db_env.DBEnvironment",
        "evaluator_method": "evaluate_task_db",
        "environment_type": "DB",
        "external_service": "docker-compose-postgres-prometheus",
    },
    "research": {
        "environment": "marble.environments.research_env.ResearchEnvironment",
        "evaluator_method": "evaluate_task_research",
        "environment_type": "Research",
        "external_service": None,
    },
}


def read_registry(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        case_id = str(entry.get("case_id") or "")
        if not case_id:
            raise ValueError(f"runtime registry line {line_number} has no case_id")
        if case_id in entries:
            raise ValueError(f"duplicate runtime registry case_id: {case_id}")
        entries[case_id] = entry
    return entries


def _validate_osworld_environment_smoke(entry: dict[str, Any]) -> bool:
    checks = entry.get("checks") or {}
    required = {
        "official_config_bound",
        "upstream_dispatch_bound",
        "provider_launch_configuration_resolved",
        "local_runtime_started",
        "reset_reproducible",
        "local_state_changed",
        "evaluator_control_path_scored",
        "audit_chain_valid",
    }
    environment = entry.get("environment") or {}
    score_probe = entry.get("score_probe") or {}
    checkpoint = entry.get("checkpoint_smoke") or {}
    return all((
        entry.get("benchmark") == "OSWorld",
        entry.get("execution_scope") == INFRASTRUCTURE_SMOKE_SCOPE,
        all(checks.get(name) is True for name in required),
        checks.get("real_vm_executed") is False,
        checks.get("model_episode_executed") is False,
        checks.get("official_task_setup_executed") is False,
        checks.get("official_gold_metric_executed") is False,
        environment.get("adapter") == "async_rbench.osworld_runtime.LocalOSWorldEnvironment",
        environment.get("scope") == "infrastructure_only",
        environment.get("real_vm") is False,
        environment.get("model_episode") is False,
        score_probe.get("kind") == "official_terminal_fail_control_path",
        score_probe.get("native_metric_executed") is False,
        score_probe.get("real_vm_executed") is False,
        score_probe.get("model_episode") is False,
        isinstance(score_probe.get("score"), (int, float)),
        score_probe.get("score") == score_probe.get("expected_score"),
        bool(checkpoint.get("baseline_revision")),
        checkpoint.get("checkpoint_revision") != checkpoint.get("baseline_revision"),
        checkpoint.get("restored_revision") == checkpoint.get("baseline_revision"),
    ))


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value) <= _SHA256_HEX
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_marble_control_plane(control_plane: Any) -> bool:
    if not isinstance(control_plane, dict):
        return False
    state_fields = (
        "started_state_sha256",
        "baseline_state_sha256",
        "checkpoint_state_sha256",
        "reset_state_sha256",
    )
    if not all(_valid_sha256(control_plane.get(field)) for field in state_fields):
        return False
    if control_plane["checkpoint_state_sha256"] == control_plane["baseline_state_sha256"]:
        return False
    if control_plane["reset_state_sha256"] != control_plane["baseline_state_sha256"]:
        return False
    transcript = control_plane.get("transcript_event") or {}
    if not all((
        transcript.get("kind") == "environment_healthcheck",
        transcript.get("actor_kind") == "infrastructure_control_plane",
        transcript.get("task_action") is False,
        transcript.get("sequence") == 1,
        transcript.get("logical_clock") == 1,
        (transcript.get("provenance") or {}).get("execution_scope") == INFRASTRUCTURE_SMOKE_SCOPE,
    )):
        return False
    audit = control_plane.get("audit")
    expected_events = (
        "control_plane_started",
        "environment_reset",
        "healthcheck_transcript_appended",
        "environment_reset",
    )
    if not isinstance(audit, list) or len(audit) != len(expected_events):
        return False
    previous = "0" * 64
    for record, event in zip(audit, expected_events):
        if not isinstance(record, dict) or record.get("event") != event:
            return False
        if record.get("previous_sha256") != previous or not _valid_sha256(record.get("state_sha256")):
            return False
        digest = record.get("record_sha256")
        if not _valid_sha256(digest):
            return False
        body = {key: value for key, value in record.items() if key != "record_sha256"}
        if _canonical_sha256(body) != digest:
            return False
        previous = digest
    return all((
        control_plane.get("adapter") == "LocalMarbleEnvironment",
        control_plane.get("upstream_engine_executed") is False,
    ))


def _validate_marble_environment_smoke(entry: dict[str, Any]) -> bool:
    checks = entry.get("checks") or {}
    required_checks = {
        "official_source_record_bound",
        "source_record_hash_verified",
        "hydrated_config_loaded",
        "config_entrypoint_resolved",
        "engine_entrypoint_resolved",
        "environment_entrypoint_resolved",
        "evaluator_entrypoint_resolved",
        "scenario_evaluator_bound",
        "offline_provider_healthcheck",
        "zero_external_model_calls",
        "local_control_plane_started",
        "environment_reset_reproducible",
        "native_healthcheck_transcript_appended",
        "native_state_digest_changed",
        "control_plane_audit_chain_valid",
    }
    scenario = str(entry.get("scenario") or "")
    expected = _MARBLE_BINDINGS.get(scenario)
    if expected is None:
        return False
    bindings = entry.get("bindings") or {}
    environment = entry.get("environment") or {}
    source = entry.get("source_evidence") or {}
    provider = entry.get("provider_probe") or {}
    claims = entry.get("claims") or {}
    launcher = entry.get("real_episode_launcher") or {}
    source_hashes = (
        source.get("record_sha256"),
        source.get("official_task_sha256"),
        source.get("native_config_sha256"),
        source.get("native_case_sha256"),
    )
    return all((
        entry.get("benchmark") == "MultiAgentBench",
        entry.get("schema_version") == "source-native-marble-environment-smoke-v1",
        entry.get("execution_scope") == INFRASTRUCTURE_SMOKE_SCOPE,
        entry.get("adapter") == "LocalMarbleEnvironment",
        entry.get("upstream_engine_executed") is False,
        all(checks.get(name) is True for name in required_checks),
        bindings.get("config") == "marble.configs.config.Config",
        bindings.get("engine") == "marble.engine.engine.Engine",
        bindings.get("environment") == expected["environment"],
        bindings.get("evaluator") == "marble.evaluator.evaluator.Evaluator",
        bindings.get("evaluator_method") == expected["evaluator_method"],
        environment.get("scenario") == scenario,
        environment.get("type") == expected["environment_type"],
        environment.get("external_service") == expected["external_service"],
        isinstance(source.get("jsonl_path"), str) and bool(source["jsonl_path"]),
        isinstance(source.get("line_number"), int) and source["line_number"] > 0,
        all(_valid_sha256(value) for value in source_hashes),
        provider.get("provider") == "offline/deterministic-healthcheck",
        provider.get("network_calls") == 0,
        _valid_sha256(provider.get("request_sha256")),
        _valid_sha256(provider.get("response_sha256")),
        claims.get("model_episode_executed") is False,
        claims.get("gold_evaluator_executed") is False,
        claims.get("task_scored") is False,
        claims.get("formal_promotion_ready") is False,
        isinstance(launcher.get("command"), list) and bool(launcher["command"]),
        launcher.get("preflight") == "fail_closed",
        _valid_sha256(entry.get("evidence_sha256")),
        _valid_marble_control_plane(entry.get("control_plane")),
        _canonical_sha256({key: value for key, value in entry.items() if key != "evidence_sha256"})
        == entry.get("evidence_sha256"),
    ))


SMOKE_PROFILE_VALIDATORS: dict[str, Callable[[dict[str, Any]], bool]] = {
    OSWORLD_SMOKE_PROFILE: _validate_osworld_environment_smoke,
    MARBLE_SMOKE_PROFILE: _validate_marble_environment_smoke,
}


def _validate_osworld_native_environment(entry: dict[str, Any]) -> bool:
    checks = entry.get("checks") or {}
    provider = entry.get("provider_preflight") or {}
    setup = entry.get("setup_probe") or {}
    evaluator = entry.get("evaluator_probe") or {}
    wait = entry.get("wait_probe") or {}
    reset = entry.get("reset_probe") or {}
    kvm = entry.get("kvm_probe") or {}
    adapter = entry.get("runtime_compatibility_adapter") or {}
    provider_details = provider.get("details") or {}
    score = evaluator.get("score")
    score_is_finite = (
        isinstance(score, (int, float))
        and not isinstance(score, bool)
        and float("-inf") < float(score) < float("inf")
    )

    setup_calls = setup.get("calls")
    phase_results = setup.get("phase_results") or {}
    setup_phases = {
        "first_reset_task_setup",
        "official_evaluator_postconfig",
        "second_reset_task_setup",
    }
    if not isinstance(setup_calls, list) or not setup_calls:
        return False
    setup_calls_valid = all(
        isinstance(record, dict)
        and record.get("phase") in setup_phases
        and isinstance(record.get("config_count"), int)
        and not isinstance(record.get("config_count"), bool)
        and record.get("config_count") >= 0
        and _valid_sha256(record.get("config_sha256"))
        and record.get("entered") is True
        and record.get("completed") is True
        and isinstance(record.get("returned_true"), bool)
        and "exception_type" not in record
        for record in setup_calls
    )
    setup_phases_valid = all(
        isinstance(phase_results.get(phase), dict)
        and phase_results[phase].get("call_count")
        == sum(record.get("phase") == phase for record in setup_calls)
        and isinstance(phase_results[phase].get("call_count"), int)
        and phase_results[phase].get("call_count") > 0
        and phase_results[phase].get("all_calls_completed") is True
        and phase_results[phase].get("last_call_returned_true") is True
        for phase in setup_phases
    )

    bound = evaluator.get("bound_dispatch") or {}
    trace = evaluator.get("execution_trace")
    if not isinstance(trace, list):
        return False
    binding_kinds = {
        "result_getter": bound.get("result_getter_bindings"),
        "expected_getter": bound.get("expected_getter_bindings"),
        "metric": bound.get("metric_bindings"),
    }
    if not all(isinstance(bindings, list) for bindings in binding_kinds.values()):
        return False
    bindings_valid = all(
        isinstance(binding, dict)
        and isinstance(binding.get("index"), int)
        and not isinstance(binding.get("index"), bool)
        and binding.get("index") >= 0
        and isinstance(binding.get("path"), str)
        and bool(binding.get("path"))
        for bindings in binding_kinds.values()
        for binding in bindings
    )
    binding_sets = {
        kind: {(binding["index"], binding["path"]) for binding in bindings}
        for kind, bindings in binding_kinds.items()
    } if bindings_valid else {kind: set() for kind in binding_kinds}
    trace_valid = all(
        isinstance(record, dict)
        and record.get("kind") in binding_kinds
        and isinstance(record.get("index"), int)
        and not isinstance(record.get("index"), bool)
        and record.get("index") >= 0
        and isinstance(record.get("path"), str)
        and bool(record.get("path"))
        and record.get("entered") is True
        and record.get("completed") is True
        and "exception_type" not in record
        and (record.get("index"), record.get("path"))
        in binding_sets.get(record.get("kind"), set())
        for record in trace
    )
    completed = {
        (record["kind"], record["index"], record["path"])
        for record in trace
    } if trace_valid else set()
    completed_indices = {
        kind: {index for record_kind, index, _ in completed if record_kind == kind}
        for kind in binding_kinds
    }
    expected_required = evaluator.get("expected_getter_required_indices")
    expected_required_valid = (
        isinstance(expected_required, list)
        and len(expected_required) == len(set(expected_required))
        and all(
            isinstance(index, int)
            and not isinstance(index, bool)
            and index >= 0
            and index in {binding["index"] for binding in binding_kinds["expected_getter"]}
            for index in expected_required
        )
    )
    metric_pairs_valid = expected_required_valid and all(
        index in completed_indices["result_getter"]
        and (index not in expected_required or index in completed_indices["expected_getter"])
        for index in completed_indices["metric"]
    )
    infeasible = evaluator.get("infeasible") is True
    evaluator_path_valid = (
        all((
            evaluator.get("metric_applicability") == "not_applicable_infeasible",
            evaluator.get("evaluator_func") == "infeasible",
            score == 0.0,
            evaluator.get("result_getter_executed") is False,
            evaluator.get("expected_getter_executed") is False,
            evaluator.get("gold_metric_executed") is False,
            trace == [],
            entry.get("official_gold_metric_executed") is False,
            checks.get("case_specific_result_getter_executed") is False,
            checks.get("case_specific_gold_metric_executed") is False,
        ))
        if infeasible
        else all((
            evaluator.get("metric_applicability") == "case_specific_gold_metric",
            evaluator.get("evaluator_func") != "infeasible",
            isinstance(evaluator.get("evaluator_func"), (str, list)),
            evaluator.get("result_getter_executed") is True,
            evaluator.get("gold_metric_executed") is True,
            bool(completed_indices["result_getter"]),
            bool(completed_indices["metric"]),
            metric_pairs_valid,
            entry.get("official_gold_metric_executed") is True,
            checks.get("case_specific_result_getter_executed") is True,
            checks.get("case_specific_gold_metric_executed") is True,
        ))
    )
    first_container = reset.get("first_container_id")
    second_container = reset.get("second_container_id")
    containers_valid = all((
        isinstance(first_container, str),
        isinstance(second_container, str),
        len(first_container) == 64,
        len(second_container) == 64,
        set(first_container) <= _SHA256_HEX,
        set(second_container) <= _SHA256_HEX,
        first_container != second_container,
    ))
    kvm_exit = kvm.get("exit_code")
    kvm_device_available = kvm.get("device_available")
    kvm_exit_valid = (
        isinstance(kvm_exit, int)
        and not isinstance(kvm_exit, bool)
        and ((kvm_exit == 0) is kvm_device_available)
    ) or (kvm_exit is None and kvm_device_available is False)
    kvm_command = kvm.get("command")
    kvm_command_valid = (
        isinstance(kvm_command, list)
        and all(isinstance(part, str) for part in kvm_command)
        and "run" in kvm_command
        and "--device" in kvm_command
        and "/dev/kvm" in kvm_command
        and "test -c /dev/kvm" in kvm_command
    )
    attestation_checks = provider_details.get("asset_attestation_checks") or {}
    required_attestation_checks = {
        "schema_valid", "assets_ready", "qcow2_path_matches",
        "qcow2_file_present", "qcow2_size_matches", "qcow2_mtime_matches",
        "qcow2_hash_attested", "docker_digest_attested",
        "docker_digest_present", "docker_latest_matches_digest",
    }
    attestation_checks_valid = all(
        attestation_checks.get(name) is True for name in required_attestation_checks
    )
    bootstrap_checks = provider_details.get("python_bootstrap_checks") or {}
    required_bootstrap_checks = {
        "schema_valid", "report_passed", "interpreter_matches",
        "interpreter_is_supported_cpython", "interpreter_prefix_matches",
        "interpreter_base_prefix_matches", "venv_prefix_matches",
        "upstream_root_matches", "venv_isolated", "lock_path_matches",
        "lock_sha256_matches", "environment_fingerprint_valid",
        "installer_configuration_valid", "installed_distributions_match",
        "lock_installation_valid", "upstream_constraints_valid",
        "runtime_versions_authoritative", "pip_check_passed",
        "desktop_env_import_bound", "psutil_import_isolated",
        "docker_provider_import_bound",
    }
    bootstrap_checks_valid = all(
        bootstrap_checks.get(name) is True for name in required_bootstrap_checks
    )
    wait_reward = wait.get("reward")
    wait_reward_valid = (
        isinstance(wait_reward, (int, float))
        and not isinstance(wait_reward, bool)
        and float("-inf") < float(wait_reward) < float("inf")
        and float(wait_reward) == 0.0
    )
    return all((
        entry.get("benchmark") == "OSWorld",
        entry.get("schema_version") == "osworld-native-environment-v2",
        entry.get("execution_scope") == NATIVE_RUNTIME_SCOPE,
        entry.get("real_vm_executed") is True,
        entry.get("official_task_setup_executed") is True,
        entry.get("official_evaluator_executed") is True,
        entry.get("model_episode_executed") is False,
        entry.get("fallback_used") is False,
        all(checks.get(name) is True for name in {
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
        }),
        provider.get("configuration_resolved") is True,
        provider.get("launch_ready") is True,
        provider.get("launch_attempted") is True,
        provider.get("launch_succeeded") is True,
        provider.get("provider") == "docker",
        not provider.get("blockers"),
        provider_details.get("asset_attestation_verified") is True,
        _valid_sha256(provider_details.get("asset_attestation_sha256")),
        provider_details.get("asset_attestation_present") is True,
        attestation_checks_valid,
        provider_details.get("python_bootstrap_report_present") is True,
        _valid_sha256(provider_details.get("python_bootstrap_report_sha256")),
        provider_details.get("python_environment_lock_present") is True,
        _valid_sha256(provider_details.get("python_environment_lock_sha256")),
        provider_details.get("python_environment_isolated") is True,
        provider_details.get("python_pip_check_passed") is True,
        provider_details.get("python_desktop_env_import_bound") is True,
        provider_details.get("python_docker_provider_import_bound") is True,
        provider_details.get("python_psutil_import_isolated") is True,
        provider_details.get("python_bootstrap_verified") is True,
        bootstrap_checks_valid,
        setup_calls_valid,
        setup_phases_valid,
        kvm.get("attempted") is True,
        isinstance(kvm_device_available, bool),
        kvm_exit_valid,
        kvm_command_valid,
        adapter.get("scope") == "desktop_env.providers.docker.provider.os",
        adapter.get("enabled") is kvm_device_available,
        adapter.get("kvm_exists_overridden") is kvm_device_available,
        adapter.get("provider_module_os_replaced") is kvm_device_available,
        adapter.get("global_os_patched") is False,
        adapter.get("upstream_source_modified") is False,
        adapter.get("acceleration_mode") == (
            "kvm" if kvm.get("device_available") else "tcg"
        ),
        evaluator.get("official_evaluator_executed") is True,
        evaluator.get("action_history_empty_before") is True,
        evaluator.get("action_history_empty_after") is True,
        evaluator.get("score_numeric_finite") is True,
        evaluator.get("score_raw_type") != "bool",
        score_is_finite,
        _valid_sha256(evaluator.get("task_evaluator_sha256")),
        _valid_sha256(entry.get("official_task_config_sha256")),
        _valid_sha256(entry.get("official_evaluator_source_sha256")),
        evaluator.get("all_trace_records_completed") is True,
        evaluator.get("metric_getter_index_pairs_valid") is True,
        evaluator.get("dispatch_trace_valid") is True,
        bindings_valid,
        trace_valid,
        evaluator_path_valid,
        wait.get("action") == "WAIT",
        wait_reward_valid,
        wait.get("done") is False,
        wait.get("info") == {},
        wait.get("environment_used_after_wait") is True,
        wait.get("action_history_before") == [],
        wait.get("action_history_after") == ["WAIT"],
        reset.get("second_reset_completed") is True,
        reset.get("provider") == "docker",
        reset.get("observation_equality_required") is False,
        reset.get("container_replaced") is True,
        reset.get("action_history_cleared") is True,
        reset.get("lifecycle_phase_order") == [
            "first_reset", "official_evaluator", "wait", "second_reset",
        ],
        containers_valid,
        _valid_sha256(reset.get("first_observation_sha256")),
        _valid_sha256(reset.get("second_observation_sha256")),
        _valid_sha256(entry.get("evidence_sha256")),
        _canonical_sha256({
            key: value
            for key, value in entry.items()
            if key not in {
                "evidence_sha256",
                "environment_smoke",
                "model_execution",
                "native_environment_initialization",
            }
        })
        == entry.get("evidence_sha256"),
        "failure" not in entry,
        "close_failure" not in entry,
    ))


NATIVE_RUNTIME_PROFILE_VALIDATORS: dict[str, Callable[[dict[str, Any]], bool]] = {
    OSWORLD_NATIVE_PROFILE: _validate_osworld_native_environment,
}


def register_native_runtime_profile(
    name: str, validator: Callable[[dict[str, Any]], bool]
) -> None:
    """Register a fail-closed validator for real native-runtime evidence."""

    if not isinstance(name, str) or not name.strip():
        raise ValueError("native runtime profile name is required")
    if not callable(validator):
        raise TypeError("native runtime profile validator must be callable")
    if name in NATIVE_RUNTIME_PROFILE_VALIDATORS:
        raise ValueError(f"native runtime profile already registered: {name}")
    NATIVE_RUNTIME_PROFILE_VALIDATORS[name] = validator


def environment_smoke_qualification(
    entry: dict[str, Any] | None, *, benchmark: str, source_task_id: str
) -> tuple[bool, str | None]:
    if entry is None:
        return False, "case_environment_smoke_not_validated"
    smoke = (
        entry
        if entry.get("status") == ENVIRONMENT_SMOKE_READY_STATUS
        else entry.get("environment_smoke")
    )
    if not isinstance(smoke, dict):
        return False, "case_environment_smoke_not_validated"
    if smoke.get("benchmark") != benchmark or str(smoke.get("source_task_id")) != str(source_task_id):
        return False, "runtime_registry_source_mismatch"
    if smoke.get("status") != ENVIRONMENT_SMOKE_READY_STATUS:
        return False, "case_environment_smoke_not_validated"
    validator = SMOKE_PROFILE_VALIDATORS.get(str(smoke.get("qualification_profile") or ""))
    if validator is None or not validator(smoke):
        return False, "case_environment_smoke_validation_incomplete"
    return True, None


def native_environment_initialization_qualification(
    entry: dict[str, Any] | None, *, benchmark: str, source_task_id: str
) -> tuple[bool, str | None]:
    """Validate real initialization evidence that is still short of runtime readiness."""

    if entry is None:
        return False, "native_environment_initialization_not_validated"
    candidate = (
        entry
        if entry.get("status") == NATIVE_ENVIRONMENT_INITIALIZATION_STATUS
        else entry.get("native_environment_initialization")
    )
    if not isinstance(candidate, dict):
        return False, "native_environment_initialization_not_validated"
    if candidate.get("benchmark") != benchmark or str(candidate.get("source_task_id")) != str(source_task_id):
        return False, "runtime_registry_source_mismatch"
    if candidate.get("qualification_profile") != MARBLE_NATIVE_INITIALIZATION_PROFILE:
        return False, "native_environment_initialization_incomplete"
    from .marble_runtime import validate_native_environment_evidence

    valid, _ = validate_native_environment_evidence(candidate)
    return (True, None) if valid else (False, "native_environment_initialization_incomplete")


def qualification(entry: dict[str, Any] | None, *, benchmark: str, source_task_id: str) -> tuple[bool, str | None]:
    if entry is None:
        return False, "case_runtime_not_validated"
    if entry.get("benchmark") != benchmark or str(entry.get("source_task_id")) != str(source_task_id):
        return False, "runtime_registry_source_mismatch"
    checks = entry.get("checks") or {}
    if entry.get("status") == ENVIRONMENT_SMOKE_READY_STATUS:
        smoke_valid, _ = environment_smoke_qualification(
            entry, benchmark=benchmark, source_task_id=source_task_id
        )
        return (
            (False, "environment_smoke_only_not_native_runtime")
            if smoke_valid
            else (False, "case_runtime_validation_incomplete")
        )
    if entry.get("status") == NATIVE_ENVIRONMENT_INITIALIZATION_STATUS:
        initialized, _ = native_environment_initialization_qualification(
            entry, benchmark=benchmark, source_task_id=source_task_id
        )
        return (
            (False, "native_environment_initialization_only_not_runtime_ready")
            if initialized
            else (False, "case_runtime_validation_incomplete")
        )
    if entry.get("status") == NATIVE_RUNTIME_READY_STATUS:
        if entry.get("execution_scope") != NATIVE_RUNTIME_SCOPE:
            return False, "runtime_registry_execution_scope_invalid"
        validator = NATIVE_RUNTIME_PROFILE_VALIDATORS.get(
            str(entry.get("qualification_profile") or "")
        )
        return (
            (True, None)
            if validator is not None and validator(entry)
            else (False, "case_runtime_validation_incomplete")
        )
    if entry.get("status") != READY_STATUS:
        return False, "case_runtime_validation_incomplete"
    if benchmark != "SWE-bench" or entry.get("schema_version") != "source-native-runtime-qualification-v1":
        return False, "case_runtime_validation_incomplete"
    if entry.get("execution_scope") not in {None, INFRASTRUCTURE_SMOKE_SCOPE}:
        return False, "runtime_registry_execution_scope_invalid"
    if not all(checks.get(name) is True for name in _LEGACY_INFRASTRUCTURE_CHECKS):
        return False, "case_runtime_validation_incomplete"
    return True, None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_execution_validated(
    entry: dict[str, Any] | None, *, evidence_root: Path | None = None
) -> bool:
    """Accept only explicit, complete model-episode evidence.

    Environment, gold and checkpoint smoke are intentionally insufficient.
    """

    if entry is None:
        return False
    execution = entry.get("model_execution")
    if not isinstance(execution, dict):
        return False
    if execution.get("status") != MODEL_EXECUTION_STATUS:
        return False
    if execution.get("execution_scope") != MODEL_EPISODE_SCOPE:
        return False
    if execution.get("mode") not in MODEL_EXECUTION_MODES:
        return False
    for field in ("episode_id", "model_id"):
        if not isinstance(execution.get(field), str) or not execution[field].strip():
            return False
    evidence = execution.get("evidence")
    if not isinstance(evidence, dict):
        return False
    if not isinstance(evidence.get("path"), str) or not evidence["path"].strip():
        return False
    if evidence.get("path_exists") is not True or evidence.get("sha256_verified") is not True:
        return False
    digest = evidence.get("sha256")
    structurally_valid = (
        isinstance(digest, str)
        and len(digest) == 64
        and set(digest.lower()) <= _SHA256_HEX
    )
    if not structurally_valid:
        return False
    if evidence_root is None:
        # Self-reported path/hash booleans are never sufficient on their own.
        return False
    root = evidence_root.resolve()
    evidence_path = Path(evidence["path"])
    if evidence_path.is_absolute():
        # Keep registry evidence portable and prevent callers from blessing an
        # arbitrary host file even when it happens to be below evidence_root.
        return False
    target = (root / evidence_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return target.is_file() and _sha256_file(target) == digest.lower()


_STATUS_RANK = {
    NATIVE_RUNTIME_READY_STATUS: 3,
    NATIVE_ENVIRONMENT_INITIALIZATION_STATUS: 2,
    READY_STATUS: 4,
    ENVIRONMENT_SMOKE_READY_STATUS: 1,
}


def merge_registry_entries(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Merge evidence without allowing smoke to downgrade native/model proof."""

    for field in ("case_id", "benchmark", "source_task_id"):
        if str(existing.get(field) or "") != str(incoming.get(field) or ""):
            raise ValueError(f"runtime registry merge identity mismatch: {field}")
    existing_model = existing.get("model_execution")
    incoming_model = incoming.get("model_execution")
    if existing_model is not None and incoming_model is not None and existing_model != incoming_model:
        raise ValueError(f"conflicting model_execution evidence for {existing.get('case_id')}")

    existing_rank = _STATUS_RANK.get(str(existing.get("status") or ""), 0)
    incoming_rank = _STATUS_RANK.get(str(incoming.get("status") or ""), 0)
    source = incoming if incoming_rank >= existing_rank else existing
    merged = json.loads(json.dumps(source))

    model = incoming_model if incoming_model is not None else existing_model
    if model is not None:
        merged["model_execution"] = json.loads(json.dumps(model))

    incoming_smoke = (
        incoming
        if incoming.get("status") == ENVIRONMENT_SMOKE_READY_STATUS
        else incoming.get("environment_smoke")
    )
    existing_smoke = (
        existing
        if existing.get("status") == ENVIRONMENT_SMOKE_READY_STATUS
        else existing.get("environment_smoke")
    )
    smoke = incoming_smoke if isinstance(incoming_smoke, dict) else existing_smoke
    if merged.get("status") != ENVIRONMENT_SMOKE_READY_STATUS and isinstance(smoke, dict):
        merged["environment_smoke"] = json.loads(json.dumps(smoke))
    else:
        merged.pop("environment_smoke", None)

    incoming_native = (
        incoming
        if incoming.get("status") == NATIVE_RUNTIME_READY_STATUS
        else incoming.get("native_environment")
    )
    existing_native = (
        existing
        if existing.get("status") == NATIVE_RUNTIME_READY_STATUS
        else existing.get("native_environment")
    )
    native = incoming_native if isinstance(incoming_native, dict) else existing_native
    if merged.get("status") != NATIVE_RUNTIME_READY_STATUS and isinstance(native, dict):
        merged["native_environment"] = json.loads(json.dumps(native))
    else:
        merged.pop("native_environment", None)

    incoming_initialization = (
        incoming
        if incoming.get("status") == NATIVE_ENVIRONMENT_INITIALIZATION_STATUS
        else incoming.get("native_environment_initialization")
    )
    existing_initialization = (
        existing
        if existing.get("status") == NATIVE_ENVIRONMENT_INITIALIZATION_STATUS
        else existing.get("native_environment_initialization")
    )
    initialization = (
        incoming_initialization
        if isinstance(incoming_initialization, dict)
        else existing_initialization
    )
    if (
        merged.get("status") != NATIVE_ENVIRONMENT_INITIALIZATION_STATUS
        and isinstance(initialization, dict)
    ):
        merged["native_environment_initialization"] = json.loads(json.dumps(initialization))
    else:
        merged.pop("native_environment_initialization", None)
    return merged


def effective_execution_scope(entry: dict[str, Any] | None) -> str:
    """Normalize legacy infrastructure evidence for report accounting."""

    if entry is None:
        return "unregistered"
    scope = entry.get("execution_scope")
    if isinstance(scope, str) and scope:
        return scope
    if entry.get("status") == READY_STATUS:
        return NATIVE_RUNTIME_SCOPE
    return "unspecified"


def synchronize_runtime_metadata(
    manifest: Iterable[dict[str, Any]],
    production_report: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    *,
    model_evidence_root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Reconcile runtime-only manifest/report fields from registry evidence.

    All identities are validated before returning replacement payloads.
    Missing evidence remains a fail-closed blocker; unknown or mismatched
    evidence aborts the entire synchronization.
    """

    rows = [dict(row) for row in manifest]
    manifest_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, 1):
        case_id = str(row.get("case_id") or "")
        benchmark_name = str(row.get("benchmark") or "")
        source_id = str(row.get("source_task_id") or "")
        if not case_id or not benchmark_name or not source_id:
            raise ValueError(f"manifest row {index} has incomplete runtime identity")
        if case_id in manifest_by_id:
            raise ValueError(f"duplicate manifest case_id: {case_id}")
        manifest_by_id[case_id] = row

    unknown = sorted(set(registry) - set(manifest_by_id))
    if unknown:
        preview = ", ".join(unknown[:5])
        raise ValueError(f"runtime registry contains case_id values outside manifest: {preview}")
    for case_id, entry in registry.items():
        row = manifest_by_id[case_id]
        if entry.get("benchmark") != row["benchmark"]:
            raise ValueError(f"runtime registry benchmark mismatch for {case_id}")
        if str(entry.get("source_task_id") or "") != str(row["source_task_id"]):
            raise ValueError(f"runtime registry source_task_id mismatch for {case_id}")

    status_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    ready_benchmark_counts: Counter[str] = Counter()
    smoke_benchmark_counts: Counter[str] = Counter()
    initialization_benchmark_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    model_benchmark_counts: Counter[str] = Counter()
    for row in rows:
        case_id = str(row["case_id"])
        entry = registry.get(case_id)
        runtime_ready, runtime_blocker = qualification(
            entry,
            benchmark=str(row["benchmark"]),
            source_task_id=str(row["source_task_id"]),
        )
        smoke_ready, _ = environment_smoke_qualification(
            entry,
            benchmark=str(row["benchmark"]),
            source_task_id=str(row["source_task_id"]),
        )
        initialization_ready, _ = native_environment_initialization_qualification(
            entry,
            benchmark=str(row["benchmark"]),
            source_task_id=str(row["source_task_id"]),
        )
        row["runtime_ready"] = runtime_ready
        row["runtime_blocker"] = runtime_blocker
        if runtime_ready:
            ready_benchmark_counts[str(row["benchmark"])] += 1
        elif runtime_blocker:
            blocker_counts[runtime_blocker] += 1
        if smoke_ready:
            smoke_benchmark_counts[str(row["benchmark"])] += 1
        if initialization_ready:
            initialization_benchmark_counts[str(row["benchmark"])] += 1
        status_counts[str(entry.get("status") or "unspecified") if entry else "unregistered"] += 1
        scope_counts[effective_execution_scope(entry)] += 1
        if model_execution_validated(entry, evidence_root=model_evidence_root):
            model_benchmark_counts[str(row["benchmark"])] += 1

    report = dict(production_report)
    if "spec_ready_count" in report and report["spec_ready_count"] != len(rows):
        raise ValueError("production report spec_ready_count does not match manifest")
    report["environment_smoke_ready_count"] = sum(smoke_benchmark_counts.values())
    report["environment_smoke_ready_benchmark_counts"] = dict(sorted(smoke_benchmark_counts.items()))
    report["native_environment_initialization_count"] = sum(
        initialization_benchmark_counts.values()
    )
    report["native_environment_initialization_benchmark_counts"] = dict(
        sorted(initialization_benchmark_counts.items())
    )
    report["runtime_ready_count"] = sum(ready_benchmark_counts.values())
    report["runtime_ready_benchmark_counts"] = dict(sorted(ready_benchmark_counts.items()))
    report["runtime_blocker_counts"] = dict(sorted(blocker_counts.items()))
    report["runtime_registry_status_counts"] = dict(sorted(status_counts.items()))
    report["runtime_execution_scope_counts"] = dict(sorted(scope_counts.items()))
    report["runtime_executed_count"] = sum(model_benchmark_counts.values())
    report["runtime_executed_benchmark_counts"] = dict(sorted(model_benchmark_counts.items()))
    summary = {
        "manifest_count": len(rows),
        "registry_count": len(registry),
        "environment_smoke_ready_count": report["environment_smoke_ready_count"],
        "environment_smoke_ready_benchmark_counts": report["environment_smoke_ready_benchmark_counts"],
        "native_environment_initialization_count": report["native_environment_initialization_count"],
        "native_environment_initialization_benchmark_counts": report[
            "native_environment_initialization_benchmark_counts"
        ],
        "runtime_ready_count": report["runtime_ready_count"],
        "runtime_ready_benchmark_counts": report["runtime_ready_benchmark_counts"],
        "runtime_registry_status_counts": report["runtime_registry_status_counts"],
        "runtime_execution_scope_counts": report["runtime_execution_scope_counts"],
        "runtime_executed_count": report["runtime_executed_count"],
        "runtime_executed_benchmark_counts": report["runtime_executed_benchmark_counts"],
    }
    return rows, report, summary


def serialize_runtime_metadata(
    manifest: Iterable[dict[str, Any]], production_report: dict[str, Any]
) -> tuple[bytes, bytes]:
    manifest_bytes = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in manifest
    ).encode("utf-8")
    report_bytes = (json.dumps(production_report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return manifest_bytes, report_bytes


def serialize_registry(entries: Iterable[dict[str, Any]]) -> bytes:
    rows = sorted(entries, key=lambda item: str(item["case_id"]))
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    ).encode("utf-8")


def replace_files_atomically(payloads: Iterable[tuple[Path, bytes]]) -> None:
    """Stage a validated artifact set, then replace with rollback on errors."""

    replacements = tuple(payloads)
    if not replacements:
        return
    paths = [path for path, _ in replacements]
    if len(paths) != len(set(paths)):
        raise ValueError("atomic replacement targets must be unique")
    staged: list[tuple[Path, Path]] = []
    originals = {path: path.read_bytes() if path.is_file() else None for path, _ in replacements}
    try:
        for path, payload in replacements:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            temp_path = Path(temporary)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temp_path, path))
        replaced: list[Path] = []
        try:
            for temporary, path in staged:
                os.replace(temporary, path)
                replaced.append(path)
        except Exception:
            for path in replaced:
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                    continue
                descriptor, temporary = tempfile.mkstemp(
                    prefix=f".{path.name}.rollback.", suffix=".tmp", dir=path.parent
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(original)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def replace_runtime_metadata_atomically(
    manifest_path: Path,
    production_report_path: Path,
    manifest_bytes: bytes,
    report_bytes: bytes,
) -> None:
    replace_files_atomically((
        (manifest_path, manifest_bytes),
        (production_report_path, report_bytes),
    ))


def write_registry(path: Path, entries: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize_registry(entries))
