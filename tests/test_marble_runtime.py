import hashlib
import json
import py_compile
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from author_local import requires_author_local

import async_rbench.marble_runtime as marble_runtime

from async_rbench.marble_runtime import (
    MARBLE_OFFLINE_PROVIDER,
    MARBLE_SMOKE_SCOPE,
    MARBLE_SMOKE_STATUS,
    PINNED_STAGING_OUTPUT_SHA256,
    PINNED_STAGING_SOURCE_SHA256,
    LocalMarbleEnvironment,
    MarbleUpstreamBindings,
    OfflineDeterministicProvider,
    discover_supported_python,
    episode_preflight,
    materialize_episode_config,
    merge_smoke_evidence,
    native_runtime_binding,
    provision_database_services,
    qualify_marble_case,
    stage_marble_runtime,
    validate_native_environment_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "artifacts/source-native-v4"
UPSTREAM_ROOT = ROOT / "upstream/marble"

_NATIVE_SOURCE_MANIFEST = requires_author_local(
    "artifacts/source-native-v4/native_manifest.jsonl",
)
_UPSTREAM_MARBLE = requires_author_local(
    "upstream/marble/marble/evaluator/evaluator.py",
)
_NATIVE_BINDING = requires_author_local(
    "artifacts/native-runtime-v4/marble_native_dependencies.lock",
    "artifacts/native-runtime-v4/marble_bootstrap_report.json",
    "artifacts/native-runtime-v4/marble_environment_smoke.jsonl",
)


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _assert_audit_chain(audit):
    previous = "0" * 64
    for record in audit:
        assert record["previous_sha256"] == previous
        body = {key: value for key, value in record.items() if key != "record_sha256"}
        assert record["record_sha256"] == _digest(body)
        previous = record["record_sha256"]


@_UPSTREAM_MARBLE
@_NATIVE_SOURCE_MANIFEST
def test_all_341_marble_cases_have_environment_smoke_lifecycle_evidence():
    manifest = [
        row
        for row in _read_jsonl(SOURCE_ROOT / "native_manifest.jsonl")
        if row["benchmark"] == "MultiAgentBench"
    ]
    assert len(manifest) == 341
    assert Counter(row["source_task_id"].split(":", 1)[0] for row in manifest) == {
        "bargaining": 96,
        "coding": 97,
        "database": 98,
        "research": 50,
    }

    bindings = MarbleUpstreamBindings(UPSTREAM_ROOT)
    evidence = []
    for row in manifest:
        entry = qualify_marble_case(
            SOURCE_ROOT / row["native_path"],
            row,
            repository_root=ROOT,
            upstream_root=UPSTREAM_ROOT,
            bindings=bindings,
        )
        evidence.append(entry)
        assert entry["status"] == MARBLE_SMOKE_STATUS
        assert entry["execution_scope"] == MARBLE_SMOKE_SCOPE
        assert entry["qualification_profile"] == "marble_environment_smoke_v1"
        assert entry["adapter"] == "LocalMarbleEnvironment"
        assert entry["upstream_engine_executed"] is False
        assert all(value is True for value in entry["checks"].values())
        assert "model_execution" not in entry
        assert entry["claims"] == {
            "model_episode_executed": False,
            "gold_evaluator_executed": False,
            "task_scored": False,
            "formal_promotion_ready": False,
        }
        control = entry["control_plane"]
        assert control["checkpoint_state_sha256"] != control["baseline_state_sha256"]
        assert control["reset_state_sha256"] == control["baseline_state_sha256"]
        event = control["transcript_event"]
        assert event["kind"] == "environment_healthcheck"
        assert event["actor_kind"] == "infrastructure_control_plane"
        assert event["task_action"] is False
        _assert_audit_chain(control["audit"])

    assert Counter(entry["scenario"] for entry in evidence) == {
        "bargaining": 96,
        "coding": 97,
        "database": 98,
        "research": 50,
    }


def test_offline_provider_refuses_task_completion():
    provider = OfflineDeterministicProvider()
    nonce = "a" * 64
    response = provider.healthcheck({"operation": "healthcheck", "nonce": nonce})
    assert response["provider"] == MARBLE_OFFLINE_PROVIDER
    assert response["network_calls"] == 0
    assert response["task_completion"] is False
    with pytest.raises(RuntimeError, match="infrastructure-smoke-only"):
        provider.complete_task("do the benchmark")


def test_local_control_plane_reset_is_reproducible_and_audited():
    control = LocalMarbleEnvironment(
        case_id="case",
        source_task_id="coding:001",
        scenario="coding",
        environment_type="Coding",
        config_sha256="b" * 64,
    )
    control.start()
    baseline = control.reset()
    provider = OfflineDeterministicProvider()
    response = provider.healthcheck({"operation": "healthcheck", "nonce": "c" * 64})
    event, checkpoint = control.append_healthcheck(response)
    assert event["task_action"] is False
    assert checkpoint != baseline
    assert control.reset() == baseline
    assert control.audit_chain_valid()
    _assert_audit_chain(control.audit)


def test_registry_merge_preserves_other_benchmarks_and_gold_entries():
    existing = [
        {
            "case_id": "osw",
            "benchmark": "OSWorld",
            "source_task_id": "osw",
            "status": "environment_smoke_validated",
        },
        {
            "case_id": "mab",
            "benchmark": "MultiAgentBench",
            "source_task_id": "coding:001",
            "status": "gold_and_checkpoint_validated",
        },
        {
            "case_id": "native",
            "benchmark": "MultiAgentBench",
            "source_task_id": "coding:002",
            "status": "native_environment_initialization_validated",
        },
    ]
    smoke = [
        {
            "case_id": "mab",
            "benchmark": "MultiAgentBench",
            "source_task_id": "coding:001",
            "status": MARBLE_SMOKE_STATUS,
        },
        {
            "case_id": "mab2",
            "benchmark": "MultiAgentBench",
            "source_task_id": "coding:003",
            "status": MARBLE_SMOKE_STATUS,
        },
        {
            "case_id": "native",
            "benchmark": "MultiAgentBench",
            "source_task_id": "coding:002",
            "status": MARBLE_SMOKE_STATUS,
        },
    ]
    merged = {row["case_id"]: row for row in merge_smoke_evidence(existing, smoke)}
    assert merged["osw"] == existing[0]
    assert merged["mab"]["status"] == "gold_and_checkpoint_validated"
    assert merged["mab2"]["status"] == MARBLE_SMOKE_STATUS
    assert merged["native"]["status"] == "native_environment_initialization_validated"
    assert merged["native"]["environment_smoke"]["status"] == MARBLE_SMOKE_STATUS


@_UPSTREAM_MARBLE
def test_temporary_staging_repairs_runtime_without_mutating_upstream(tmp_path):
    watched = [
        UPSTREAM_ROOT / "marble/evaluator/evaluator.py",
        UPSTREAM_ROOT / "marble/engine/engine.py",
        UPSTREAM_ROOT / "marble/environments/base_env.py",
        UPSTREAM_ROOT / "marble/environments/db_env.py",
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched}
    staged = stage_marble_runtime(UPSTREAM_ROOT, tmp_path / "runtime")
    manifest = json.loads((staged / "STAGING_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["upstream_mutated"] is False
    assert len(manifest["patches"]) == 6
    assert manifest["runtime_assets"][0]["kind"] == (
        "docker_compose_image_digest_pins"
    )
    assert "postgres:17@sha256:" in (
        staged / "marble/environments/db_env_docker/docker-compose.yml"
    ).read_text(encoding="utf-8")
    assert {
        patch["path"]: patch["source_sha256"] for patch in manifest["patches"]
    } == PINNED_STAGING_SOURCE_SHA256
    assert {
        patch["path"]: patch["staged_sha256"] for patch in manifest["patches"]
    } == PINNED_STAGING_OUTPUT_SHA256
    py_compile.compile(
        str(staged / "marble/evaluator/evaluator.py"), doraise=True
    )
    py_compile.compile(str(staged / "marble/engine/engine.py"), doraise=True)
    assert '["sudo", "docker", "compose"' not in (
        staged / "marble/environments/db_env.py"
    ).read_text(encoding="utf-8")
    staged_db_source = (staged / "marble/environments/db_env.py").read_text(
        encoding="utf-8"
    )
    assert "Container lifecycle is owned by run_marble_native.py --provision" in staged_db_source
    assert '["docker", "compose", "down"' not in staged_db_source
    assert '["docker", "compose", "up"' not in staged_db_source
    assert "def reset(" in (
        staged / "marble/environments/base_env.py"
    ).read_text(encoding="utf-8")
    assert before == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched
    }


@_NATIVE_SOURCE_MANIFEST
def test_real_episode_preflight_rejects_offline_provider():
    row = next(
        row
        for row in _read_jsonl(SOURCE_ROOT / "native_manifest.jsonl")
        if row["benchmark"] == "MultiAgentBench"
    )
    result = episode_preflight(
        SOURCE_ROOT / row["native_path"],
        python=sys.executable,
        model="offline/deterministic",
        evaluator_model="offline/deterministic",
        upstream_root=UPSTREAM_ROOT,
        environment={},
    )
    assert result.ready is False
    assert "model:offline_provider_is_infrastructure_smoke_only" in result.errors
    assert "evaluator:offline_provider_is_infrastructure_smoke_only" in result.errors
    assert "actual_native_environment_initialized_and_reset" not in result.checks


@_UPSTREAM_MARBLE
def test_database_readiness_probe_never_starts_or_stops_compose(tmp_path, monkeypatch):
    staged = stage_marble_runtime(UPSTREAM_ROOT, tmp_path / "runtime")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append([str(part) for part in command])
        if "ps" in command:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "port" in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(marble_runtime.shutil, "which", lambda name: "docker")
    monkeypatch.setattr(marble_runtime.subprocess, "run", fake_run)
    monkeypatch.setattr(marble_runtime, "port_is_available", lambda *_args: False)
    ready, error = marble_runtime._docker_ready(staged)
    assert ready is False
    assert error and error.startswith("marble_database_services_not_provisioned:")
    assert not any("up" in command or "down" in command for command in commands)


def test_database_provisioning_is_explicit_and_fixed_project_scoped(
    tmp_path, monkeypatch
):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    commands = []

    monkeypatch.setattr(
        marble_runtime,
        "_database_compose_context",
        lambda _root: (("docker", compose, {"COMPOSE_PROJECT_NAME": "dtbench-marble-db-runtime"}), None),
    )
    monkeypatch.setattr(
        marble_runtime,
        "_compose_service_names",
        lambda *_args, **_kwargs: (set(), None),
    )
    monkeypatch.setattr(
        marble_runtime,
        "_compose_project_host_ports",
        lambda *_args, **_kwargs: (set(), None),
    )
    monkeypatch.setattr(
        marble_runtime, "_unowned_database_port_conflicts", lambda _ports: []
    )
    monkeypatch.setattr(marble_runtime, "_database_endpoint_failures", lambda: [])
    monkeypatch.setattr(marble_runtime, "_docker_ready", lambda _root: (True, None))

    def fake_run(command, **_kwargs):
        commands.append([str(part) for part in command])
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(marble_runtime.subprocess, "run", fake_run)
    ready, error = provision_database_services(tmp_path)
    assert (ready, error) == (True, None)
    assert any("down" in command and "-v" in command for command in commands)
    assert any("up" in command and "--wait" in command for command in commands)


@_UPSTREAM_MARBLE
@_NATIVE_SOURCE_MANIFEST
def test_native_initialization_evidence_validator_pins_all_six_sources(
    tmp_path,
    monkeypatch,
):
    staged = stage_marble_runtime(UPSTREAM_ROOT, tmp_path / "runtime")
    staging = json.loads(
        (staged / "STAGING_MANIFEST.json").read_text(encoding="utf-8")
    )
    runtime_binding = {"isolated_test_runtime": True}
    monkeypatch.setattr(
        marble_runtime,
        "native_runtime_binding",
        lambda *_args, **_kwargs: (runtime_binding, None),
    )
    source_evidence = {
        "jsonl_path": "upstream/marble/multiagentbench/coding/coding_main.jsonl",
        "line_number": 1,
        "native_case_sha256": "1" * 64,
        "native_config_sha256": "2" * 64,
        "official_task_sha256": "3" * 64,
        "record_sha256": "4" * 64,
    }
    entry = {
        "schema_version": "source-native-marble-native-environment-v1",
        "case_id": "mab-native-test",
        "benchmark": "MultiAgentBench",
        "source_task_id": "coding:001",
        "scenario": "coding",
        "status": "native_environment_initialization_validated",
        "execution_scope": "native_runtime",
        "qualification_profile": "marble_native_environment_initialization_v1",
        "runtime_adapter": "temporary_portable_marble_runtime_v1",
        "source_evidence": source_evidence,
        "runtime_binding": runtime_binding,
        "checks": {
            "actual_config_loaded": True,
            "actual_engine_initialized": True,
            "actual_environment_initialized": True,
            "actual_evaluator_initialized": True,
            "environment_healthcheck_changed_state": True,
            "in_memory_control_plane_reset_reproducible": True,
            "upstream_engine_start_not_called": True,
            "zero_model_calls": True,
        },
        "call_audit": {
            "engine_start_calls": 0,
            "model_entrypoint_calls": 0,
            "patched_model_entrypoints": [
                "litellm.acompletion",
                "litellm.completion",
                "marble.llms.model_prompting.model_prompting",
                "openai.resources.chat.completions.AsyncCompletions.create",
                "openai.resources.chat.completions.Completions.create",
            ],
        },
        "bindings": {
            "config": "marble.configs.config.Config",
            "engine": "marble.engine.engine.Engine",
            "environment": "marble.environments.coding_env.CodingEnvironment",
            "evaluator": "marble.evaluator.evaluator.Evaluator",
        },
        "state_evidence": {
            "initial_state_sha256": "a" * 64,
            "healthcheck_state_sha256": "b" * 64,
            "in_memory_reset_state_sha256": "a" * 64,
            "host_state_snapshot": False,
        },
        "claims": {
            "model_episode_executed": False,
            "gold_evaluator_executed": False,
            "task_scored": False,
            "native_checkpoint_validated": False,
        },
        "materialized_config_sha256": "c" * 64,
        "runtime_staging": {
            "adapter": staging["adapter"],
            "upstream_mutated": staging["upstream_mutated"],
            "runtime_directories": staging["runtime_directories"],
            "runtime_assets": staging["runtime_assets"],
            "patches": staging["patches"],
        },
    }
    entry["evidence_sha256"] = _digest(entry)
    assert validate_native_environment_evidence(entry) == (True, None)

    merged_entry = merge_smoke_evidence(
        [entry],
        [
            {
                "case_id": entry["case_id"],
                "benchmark": "MultiAgentBench",
                "source_task_id": entry["source_task_id"],
                "status": "environment_smoke_validated",
                "execution_scope": "infrastructure_smoke",
            }
        ],
    )[0]
    assert merged_entry["environment_smoke"]["status"] == (
        "environment_smoke_validated"
    )
    assert validate_native_environment_evidence(merged_entry) == (True, None)

    from scripts.initialize_marble_collection import evidence_matches_case

    row = {
        "case_id": entry["case_id"],
        "source_task_id": entry["source_task_id"],
    }
    qualification = {"source_evidence": source_evidence}
    assert evidence_matches_case(entry, row, qualification) == (True, None)
    copied = dict(entry)
    copied["case_id"] = "mab-copied-evidence"
    copied["evidence_sha256"] = _digest(
        {key: value for key, value in copied.items() if key != "evidence_sha256"}
    )
    valid, reason = evidence_matches_case(copied, row, qualification)
    assert valid is False
    assert reason == "marble_batch_case_id_binding_mismatch"

    entry["runtime_staging"]["patches"][0]["source_sha256"] = "d" * 64
    entry["evidence_sha256"] = _digest(
        {key: value for key, value in entry.items() if key != "evidence_sha256"}
    )
    valid, reason = validate_native_environment_evidence(entry)
    assert valid is False
    assert reason == "marble_native_environment_staging_source_hash_invalid"


@_NATIVE_BINDING
def test_isolated_runtime_binding_pins_lock_report_and_imports():
    binding, error = native_runtime_binding(repository_root=ROOT)
    assert error is None
    assert binding is not None
    assert binding["python_runtime"]["version_info"][:2] == [3, 9]
    assert binding["python_runtime"]["system_site_packages"] is False
    assert binding["python_runtime"]["prefix"] != binding["python_runtime"][
        "base_prefix"
    ]
    assert binding["dependency_lock_sha256"] == binding[
        "dependency_lock_artifact_sha256"
    ]
    assert all(binding["checks"].values())


@_NATIVE_SOURCE_MANIFEST
def test_batch_resume_refuses_existing_evidence_when_runtime_is_missing(
    tmp_path,
    monkeypatch,
):
    import scripts.initialize_marble_collection as batch

    row = sorted(
        (
            row
            for row in _read_jsonl(SOURCE_ROOT / "native_manifest.jsonl")
            if row["benchmark"] == "MultiAgentBench"
            and row["source_task_id"].startswith("coding:")
        ),
        key=lambda item: item["case_id"],
    )[0]
    output = tmp_path / "batch"
    cases = output / "cases"
    cases.mkdir(parents=True)
    (cases / (row["case_id"] + ".json")).write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        batch,
        "discover_supported_python",
        lambda _preferred=None: (None, "marble_python_unavailable"),
    )
    monkeypatch.setattr(
        batch,
        "evidence_matches_case",
        lambda *_args, **_kwargs: (True, None),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "initialize_marble_collection.py",
            "--scenarios",
            "coding",
            "--limit",
            "1",
            "--resume",
            "--output",
            str(output),
        ],
    )
    assert batch.main() == 1
    report = json.loads((output / "batch_report.json").read_text(encoding="utf-8"))
    assert report["infrastructure_error"] == "marble_python_unavailable"
    assert report["resume_skipped_count"] == 0
    assert report["attempted_count"] == 1
    assert report["failed_count"] >= 1


@_NATIVE_SOURCE_MANIFEST
def test_batch_empty_selection_is_never_reported_validated(tmp_path, monkeypatch):
    import scripts.initialize_marble_collection as batch

    output = tmp_path / "empty"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "initialize_marble_collection.py",
            "--limit",
            "0",
            "--output",
            str(output),
        ],
    )
    assert batch.main() == 1
    report = json.loads((output / "batch_report.json").read_text(encoding="utf-8"))
    assert report["selected_count"] == 0
    assert report["status"] == "native_environment_initialization_incomplete"
    assert report["infrastructure_error"] == "marble_collection_selection_empty"


@_NATIVE_SOURCE_MANIFEST
def test_launcher_preflight_report_never_claims_model_episode():
    row = next(
        row
        for row in _read_jsonl(SOURCE_ROOT / "native_manifest.jsonl")
        if row["benchmark"] == "MultiAgentBench"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_marble_native.py"),
            "--case-id",
            row["case_id"],
            "--model",
            "offline/deterministic",
            "--evaluator-model",
            "offline/deterministic",
            "--preflight-only",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["execution_scope"] == "native_preflight"
    assert report["model_episode_executed"] is False
    assert report["provisioning"]["performed"] is False
    assert "actual_native_environment_initialized_and_reset" not in report["checks"]


def test_python_discovery_never_selects_an_unsupported_version():
    selected, error = discover_supported_python()
    if selected is None:
        assert error == "marble_supported_python_not_found:requires_3.9_to_3.11"
        return
    completed = __import__("subprocess").run(
        [selected, "-c", "import sys; print(sys.version_info[:2])"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() in {"(3, 9)", "(3, 10)", "(3, 11)"}


@_UPSTREAM_MARBLE
def test_materialized_config_is_ascii_safe_and_preserves_cjk_for_upstream_loader(
    tmp_path,
):
    source = tmp_path / "source.yaml"
    expected = "中文-日本語-한국어"
    source.write_text(
        "scenario: coding\ntask:\n  content: " + expected + "\n",
        encoding="utf-8",
    )
    materialized = tmp_path / "native_config.yaml"
    materialize_episode_config(
        source,
        materialized,
        model="offline/deterministic",
        evaluator_model="offline/deterministic",
    )
    assert all(byte < 128 for byte in materialized.read_bytes())

    selected, error = discover_supported_python()
    assert error is None and selected is not None
    staged = stage_marble_runtime(UPSTREAM_ROOT, tmp_path / "runtime")
    environment = __import__("os").environ.copy()
    environment["PYTHONPATH"] = str(staged)
    completed = subprocess.run(
        [
            selected,
            "-c",
            (
                "from marble.configs.config import Config; import json,sys; "
                "print(json.dumps(Config.load(sys.argv[1]).task['content']))"
            ),
            str(materialized),
        ],
        cwd=staged,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert json.loads(completed.stdout) == expected


@_NATIVE_BINDING
def test_checked_in_evidence_matches_full_qualification_output():
    entries = _read_jsonl(
        ROOT / "artifacts/native-runtime-v4/marble_environment_smoke.jsonl"
    )
    report = json.loads(
        (ROOT / "artifacts/native-runtime-v4/marble_environment_smoke_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(entries) == 341
    assert all(entry["status"] == MARBLE_SMOKE_STATUS for entry in entries)
    assert report["validated_count"] == 341
    assert report["failed_count"] == 0
    assert report["scenario_counts"] == {
        "bargaining": 96,
        "coding": 97,
        "database": 98,
        "research": 50,
    }
