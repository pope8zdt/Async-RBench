from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from async_rbench.eval_cli import _append_config, _command_entrypoint
from async_rbench.evaluation.manifest import create_manifest
from async_rbench.evaluation.runner import _case_digest
from async_rbench.evaluation.version import EVALUATION_CONTRACT_VERSION
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.spec import CaseSpec, load_case, validate_case


ROOT = Path(__file__).resolve().parents[1]


def test_case_digest_supports_legacy_and_trajectory_payload_layouts() -> None:
    digests = {
        case_dir.name: _case_digest(case_dir)
        for case_dir in sorted((ROOT / "cases").iterdir())
        if case_dir.is_dir()
    }
    assert set(digests) >= {
        "data-recovery-service",
        "gaia2-stockholm-moveout",
        "git-conflict-and-cleanup-closure",
        "scheduler-selective-replan",
        "swe-bench-selective-patch",
    }
    assert all(len(value) == 64 for value in digests.values())


def test_case_validation_rejects_unreplayable_duplicate_result_schedule() -> None:
    source = load_case(ROOT / "cases/gaia2-stockholm-moveout/public_case.yaml")
    raw = deepcopy(source.raw)
    duplicate = dict(raw["scenarios"]["async"]["events"][0])
    duplicate["id"] = "duplicate-stream"
    raw["scenarios"]["async"]["events"].append({
        **duplicate,
        "id": "duplicate-stream",
    })
    errors = validate_case(CaseSpec(path=source.path, raw=raw))
    assert any("schedules result kinds more than once" in error for error in errors)


def test_case_validation_rejects_nonempty_linear_events() -> None:
    source = load_case(ROOT / "cases/gaia2-stockholm-moveout/public_case.yaml")
    raw = deepcopy(source.raw)
    raw["scenarios"]["linear"]["events"] = [dict(raw["scenarios"]["async"]["events"][0])]
    errors = validate_case(CaseSpec(path=source.path, raw=raw))
    assert any("linear scenario must not inject" in error for error in errors)


def test_case_validation_requires_authority_scoped_event_asset() -> None:
    source = load_case(ROOT / "cases/gaia2-stockholm-moveout/public_case.yaml")
    raw = deepcopy(source.raw)
    raw["event_assets"] = {}
    errors = validate_case(CaseSpec(path=source.path, raw=raw))
    assert any("authoritative workstream" in error for error in errors)


def test_case_validation_rejects_unobservable_runtime_artifact() -> None:
    source = load_case(ROOT / "candidate_cases/nginx-live-port-conflict/public_case.yaml")
    raw = deepcopy(source.raw)
    runtime = next(item for item in raw["artifacts"] if item["id"] == "runtime_state")
    runtime.pop("observer_command", None)
    errors = validate_case(CaseSpec(path=source.path, raw=raw))
    assert any("non-filesystem artifact 'runtime_state'" in error for error in errors)


def test_participant_dockerfiles_do_not_copy_private_material() -> None:
    forbidden = ("COPY tests", "COPY oracle.sh", "upstream_solutions", "COPY run-tests.sh")
    for dockerfile in sorted((ROOT / "cases").glob("*/task/Dockerfile")):
        executable_lines = [
            line.strip() for line in dockerfile.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        content = "\n".join(executable_lines)
        assert not any(token in content for token in forbidden), dockerfile


def test_composite_instructions_publish_upstream_exact_contracts() -> None:
    distributed = (ROOT / "cases/distributed-model-runtime/task/task.yaml").read_text(encoding="utf-8")
    for required in (
        "__init__(self, in_features, out_features, bias, master_weight)",
        "train_step_pipeline_afab(model, inputs, targets, device, dtype)",
        "at most 8 unique shapes", "bucket 1 cost 3.0e11",
        "contain exactly these", "implementation_sha256",
    ):
        assert required in distributed

    secure = (ROOT / "cases/secure-release/task/task.yaml").read_text(encoding="utf-8")
    for required in (
        '"/app/bottle.py"', '"cwe-93"',
        "/etc/nginx/conf.d/benchmark-site.conf",
        "/var/log/nginx/benchmark-access.log",
        "Welcome to the benchmark webserver",
        "Page not found - Please check your URL",
    ):
        assert required in secure


def test_scaffold_config_validates_known_modes_and_rejects_unknown() -> None:
    """The config-level release check is the remaining fail-closed core.

    ``scripted_test`` and ``container_clone`` remain legitimate development and
    formal modes; only unsupported backends/workspace modes are rejected by the
    config's own validation. Protocol conformance is what
    governs whether a profile may run a formal episode.
    """
    ScaffoldConfig(
        backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
        workspace_mode="container_clone",
    ).validate()
    with pytest.raises(ValueError, match="unsupported backend"):
        ScaffoldConfig(
            backend="unknown_backend", main_model="m", child_model="m",
            workspace_mode="container_clone",
        ).validate()
    with pytest.raises(ValueError, match="workspace_mode must be"):
        ScaffoldConfig(
            backend="openai_compatible", main_model="m", child_model="m",
            workspace_mode="unknown_workspace",
        ).validate()


def test_adapter_profile_binding_compares_entrypoint_and_appends_config(tmp_path: Path) -> None:
    profile = ["python", "adapters/reference_scaffold_api.py"]
    explicit = ["C:/Python/python.exe", "adapters/reference_scaffold_api.py", "--backend", "openai_compatible"]
    mismatch = ["python", "adapters/native_agent.py"]
    assert _command_entrypoint(profile) == _command_entrypoint(explicit)
    assert _command_entrypoint(profile) != _command_entrypoint(mismatch)
    config = tmp_path / "participant.yaml"
    assert _append_config(profile, config)[-2:] == ["--config", str(config)]


def test_manifest_pins_contract_without_an_evaluation_mode() -> None:
    manifest = create_manifest(
        ["secure-release"], 1, "incentive", 2026,
        instance_keys=["secure-release::seed-1"],
    )
    assert "evaluation_mode" not in manifest
    assert manifest["evaluation_contract_version"] == EVALUATION_CONTRACT_VERSION
    assert {item["execution_mode"] for item in manifest["episodes"]} == {"linear", "async"}
    assert len(manifest["evaluation_contract_sha256"]) == 64
    digest_key = "secure-release::seed-1"
    assert len(manifest["verifier_bundle_sha256"][digest_key]) == 64
    assert len(manifest["case_bundle_sha256"][digest_key]) == 64
    assert len(manifest["episodes"]) == 2
    json.dumps(manifest)


def test_secure_private_verifier_trusts_only_exact_evaluated_repositories() -> None:
    runner = (ROOT / "cases/secure-release/task/run-tests.sh").read_text(encoding="utf-8")
    assert "git config --global --add safe.directory /app/repo" in runner
    assert "git config --global --add safe.directory /git/project.git" in runner
    assert "safe.directory '*'" not in runner


def test_secure_private_verifier_runs_all_components_without_shell_early_exit() -> None:
    runner = (ROOT / "cases/secure-release/task/run-tests.sh").read_text(encoding="utf-8")
    assert "set -e" not in runner
    for component in (
        "authority", "stale_exclusion", "downstream_rebuild", "runtime_behavior",
        "lineage_reverification", "independent_preservation",
    ):
        assert f"run_component {component} pytest" in runner
    assert "nginx ||" in runner


def test_data_recovery_composite_exposes_all_upstream_public_contracts() -> None:
    task = yaml.safe_load(
        (ROOT / "cases/data-recovery-service/task/task.yaml").read_text(encoding="utf-8")
    )
    instruction = task["instruction"]
    required_public_contract = (
        "checkpoint-only recovery branch",
            "WAL-applied recovery branch",
        "independent three-source merge branch",
        "registration_date, created_at, joined -> created_date",
        '"total_conflicts": <number>',
        "/app/kv-store.proto",
        "/app/kv_store_pb2.py",
        "/app/kv_store_pb2_grpc.py",
        "/app/server.py",
        "class named Server",
        '"recovered_sha256"',
            '"recovered_row_count": <observed final row count>',
    )
    missing = [item for item in required_public_contract if item not in instruction]
    assert not missing, f"composite instruction omitted public upstream requirements: {missing}"
    # The benchmark, not the model, owns the initial wave. The instruction must
    # state the wave is already started and must never ask the model to create it.
    assert "BENCHMARK-STARTED" in instruction
    assert "ASYNC_RBENCH_INITIAL_WAVE notice" in instruction
    assert "never be scored on having spawned the initial team" in instruction
    assert "use spawn_subagent only to re-delegate" in instruction
    assert instruction.index("INITIAL CONCURRENT WORKSTREAMS") < instruction.index("WAL RECOVERY CONTRACT")


def test_distributed_case_declares_the_three_benchmark_started_branches() -> None:
    task = yaml.safe_load(
        (ROOT / "cases/distributed-model-runtime/task/task.yaml").read_text(encoding="utf-8")
    )
    instruction = task["instruction"]
    required = (
        "tensor-parallel candidate",
        "profile constraints",
        "independently reconstructs and tunes the model",
        "BENCHMARK-STARTED",
        "ASYNC_RBENCH_INITIAL_WAVE notice",
        "never be scored on having spawned the initial team",
    )
    missing = [item for item in required if item not in instruction]
    assert not missing, f"distributed instruction omitted benchmark-started branches: {missing}"
    # The model must never be instructed to create the initial team.
    assert "wave request" not in instruction
    assert "begin with one concurrent" not in instruction


def test_event_authority_facts_are_isolated_from_initial_main_view() -> None:
    data = load_case(ROOT / "cases/data-recovery-service/public_case.yaml").raw
    distributed = load_case(ROOT / "cases/distributed-model-runtime/public_case.yaml").raw
    secure = load_case(ROOT / "cases/secure-release/public_case.yaml").raw
    assert data["event_assets"] == {"wal_recovery": ["/app/main.db-wal"]}
    assert distributed["event_assets"] == {"select_backend": ["/app/profiles/authoritative.json"]}
    assert secure["event_assets"] == {"sanitize_history": ["/app/events/authoritative-release.bundle"]}
    for case_id in ("data-recovery-service", "distributed-model-runtime", "secure-release"):
        public = yaml.safe_load(
            (ROOT / "cases" / case_id / "public_case.yaml").read_text(encoding="utf-8")
        )
        assert "event_assets" not in public
    data_instruction = (ROOT / "cases/data-recovery-service/task/task.yaml").read_text()
    distributed_instruction = (ROOT / "cases/distributed-model-runtime/task/task.yaml").read_text()
    assert "all eleven rows" not in data_instruction
    assert 'requires backend="pipeline"' not in distributed_instruction
