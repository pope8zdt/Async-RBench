from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml
import pytest

from async_rbench.evaluation import runner as runner_module
from async_rbench.evaluation.runner import EpisodeConfig
from async_rbench.evaluation.workspace_runtime import CommandResult, DisabledWorkspaceRuntime
from async_rbench import private_eval
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


class _Stdin:
    def write(self, _payload: bytes) -> None:
        return None

    async def drain(self) -> None:
        return None


class _FakeProcess:
    def __init__(self, events: list[dict]) -> None:
        self.stdin = _Stdin()
        self.stderr = asyncio.StreamReader()
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(
            b"".join(json.dumps(event).encode("utf-8") + b"\n" for event in events)
        )
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self.returncode = 0

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


class _SemanticFailingWorkspace(DisabledWorkspaceRuntime):
    def __init__(self) -> None:
        self.commands: list[str] = []

    async def child_terminal(
        self, child_id: str, command: str, timeout: int,
    ) -> CommandResult:
        self.commands.append(command)
        return CommandResult(7, "private semantic mismatch")


def _write_case(tmp_path: Path) -> Path:
    case_dir = tmp_path / "semantic-case"
    (case_dir / "private").mkdir(parents=True)
    (case_dir / "task" / "tests").mkdir(parents=True)
    (case_dir / "task" / "assets").mkdir(parents=True)
    (case_dir / "public_case.yaml").write_text(yaml.safe_dump({
        "format_version": 2,
        "case_id": "semantic-case",
        "title": "Private semantic failure does not reject",
        "task_instruction_path": "task/task.yaml",
        "workstreams": [
            {
                "id": "authority",
                "task": "Inspect the state.",
                "targets": [],
                "expected_output": "Observed state.",
                "priority": "normal",
                "required_evidence_fields": ["finding"],
                "evidence_schema": {"finding": {"type": "string"}},
                "allowed_files": [],
                "required_files": [],
                "public_result_contract": {"kind": "payload_only"},
            },
            {
                "id": "support",
                "task": "Inspect supporting state.",
                "targets": [],
                "expected_output": "Supporting observation.",
                "priority": "normal",
                "required_evidence_fields": ["finding"],
                "evidence_schema": {"finding": {"type": "string"}},
                "allowed_files": [],
                "required_files": [],
                "public_result_contract": {"kind": "payload_only"},
            },
        ],
        "artifacts": [],
        "public_checks": [],
    }, sort_keys=False), encoding="utf-8")
    (case_dir / "private" / "private_case.yaml").write_text(yaml.safe_dump({
        "format_version": 2,
        "case_id": "semantic-case",
        "classification": {
            "primary_event_theme": "partial_then_complete_result",
            "secondary_event_themes": [],
            "async_scenario_class": "result_eventful",
        },
        "capabilities": [],
        "workstream_bindings": {
            "authority": {
                "result_kind": "result_01",
                "validator_stage": "semantic_evidence",
                "validator_command": "python3 -c \"raise SystemExit(7)\"",
                "validator_timeout_sec": 30,
                "private_evidence_schema": {
                    "finding": {"type": "string", "const": "expected"},
                },
                "event_assets": [],
            },
            "support": {
                "result_kind": "result_02",
                "validator_stage": "semantic_evidence",
                "validator_command": "python3 -c \"raise SystemExit(7)\"",
                "validator_timeout_sec": 30,
                "private_evidence_schema": {
                    "finding": {"type": "string", "const": "expected"},
                },
                "event_assets": [],
            },
        },
        "result_contract": {"allowed_result_kinds": ["result_01", "result_02"]},
        "authoritative_result_kind": "result_01",
        "superseded_result_kind": "result_02",
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
        "hidden_checks": {},
        "reverification_anchors": {},
        "stale_predicate": None,
        "stale_revalidation": {},
        "information_sufficiency": [
            {
                "workstream_id": "authority",
                "public_inputs": [],
                "required_output_fields": ["finding"],
                "review_status": "reviewed",
                "requirement_ids": ["semantic-case.complete"],
            },
            {
                "workstream_id": "support",
                "public_inputs": [],
                "required_output_fields": ["finding"],
                "review_status": "reviewed",
                "requirement_ids": ["semantic-case.complete"],
            },
        ],
    }, sort_keys=False), encoding="utf-8")
    (case_dir / "task" / "task.yaml").write_text(
        yaml.safe_dump({"instruction": "Inspect the state."}), encoding="utf-8",
    )
    (case_dir / "task" / "run-tests.sh").write_text(
        "#!/bin/sh\nexit 0\n", encoding="utf-8",
    )
    (case_dir / "task" / "tests" / "semantic_checks.json").write_text(
        json.dumps({"checks": []}), encoding="utf-8",
    )
    (case_dir / "task" / "tests" / "control_flow_checks.json").write_text(
        json.dumps({"version": "1", "checks": []}), encoding="utf-8",
    )
    return case_dir


def test_private_semantic_failure_is_delivered_without_gateway_rejection(
    tmp_path: Path, monkeypatch,
) -> None:
    events = [
        {
            "type": "participant_metadata",
            "backend": "scripted_test",
            "main_model": "scripted-main",
            "child_model": "scripted-child",
            "workspace_mode": "container_clone",
            "config_sha256": "0" * 64,
        },
        {"type": "ready"},
        {
            "type": "child_spawned", "child_id": "c1",
            "parent_id": "main", "work_units": ["authority"],
        },
        {
            "type": "child_spawned", "child_id": "c2",
            "parent_id": "main", "work_units": ["support"],
        },
        {"type": "child_started", "child_id": "c1"},
        {
            "type": "child_completed",
            "child_id": "c1",
            "completion_id": "completion-1",
            "payload": {
                "summary": "observed",
                "evidence": {"finding": "expected"},
                "files": [],
            },
        },
        {
            "type": "episode_ended",
            "final_answer": "done",
            "local_status": "completed",
            "declared_task_success": True,
        },
    ]
    workspace = _SemanticFailingWorkspace()
    fake_docker = (
        lambda *_args, **_kwargs:
        type("Result", (), {"stdout": "", "returncode": 0})()
    )
    monkeypatch.setattr(runner_module, "_docker", fake_docker)
    monkeypatch.setattr(private_eval, "_docker", fake_docker)
    monkeypatch.setattr(
        runner_module, "build_workspace_runtime", lambda *_args, **_kwargs: workspace,
    )

    async def fake_subprocess(*_args, **_kwargs) -> _FakeProcess:
        return _FakeProcess(events)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    case_dir = _write_case(tmp_path)
    output_dir = tmp_path / "out"
    config = EpisodeConfig(
        episode_id="private-semantic-failure",
        case_id="semantic-case",
        execution_mode="async",
        guidance="incentive",
        agent_seed=1,
        adapter_command=["fake-adapter"],
        output_dir=output_dir,
        use_container=True,
        timeout_sec=10,
        case_dir_override=case_dir,
    )

    asyncio.run(runner_module.run_episode(ROOT, config))

    rows = [
        json.loads(line)
        for line in (output_dir / "event_source.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    semantic = [row for row in rows if row.get("type") == "child_semantic_validated"]
    assert semantic and semantic[0]["passed"] is False
    assert semantic[0]["validator_exit_code"] == 7
    assert any(row.get("type") == "result_delivered" for row in rows)
    assert not any(row.get("type") == "result_rejected" for row in rows)
    assert workspace.commands


def test_load_case_rejects_missing_validator_stage(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path)
    private_path = case_dir / "private" / "private_case.yaml"
    private = yaml.safe_load(private_path.read_text(encoding="utf-8"))
    private["workstream_bindings"]["authority"].pop("validator_stage")
    private_path.write_text(yaml.safe_dump(private, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="validator_stage is required"):
        load_case(case_dir / "public_case.yaml")


def test_load_case_rejects_unknown_validator_stage(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path)
    private_path = case_dir / "private" / "private_case.yaml"
    private = yaml.safe_load(private_path.read_text(encoding="utf-8"))
    private["workstream_bindings"]["authority"]["validator_stage"] = "mystery"
    private_path.write_text(yaml.safe_dump(private, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported validator_stage"):
        load_case(case_dir / "public_case.yaml")
