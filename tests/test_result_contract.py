from __future__ import annotations

import asyncio
import base64
import json
import shlex
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from async_rbench.evaluation.result_contract import validate_completion_contract
from async_rbench.evaluation.runner import _make_start
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.evaluation.workspace_runtime import CommandResult
from async_rbench.profiles.reference_scaffold_api.runtime import ChildRecord, SubagentManager
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


def _case() -> dict:
    return load_case(ROOT / "cases" / "data-recovery-service" / "public_case.yaml").raw


class _Workspace:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.calls: list[tuple[str, str, int]] = []

    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult:
        self.calls.append((child_id, command, timeout))
        return CommandResult(self.exit_code, "validator output")


def test_completion_contract_checks_private_evidence_and_command() -> None:
    workstream = {
        "required_evidence_fields": ["row_count"],
        "evidence_schema": {"row_count": {"type": "integer", "const": 11}},
        "allowed_files": ["/app/recovered.json"], "required_files": ["/app/recovered.json"],
        "validator_command": "verify-result", "validator_timeout_sec": 17,
    }
    event = {"child_id": "child-1", "payload": {
        "evidence": {"row_count": 11}, "files": ["/app/recovered.json"],
    }}
    workspace = _Workspace()
    result = asyncio.run(validate_completion_contract(workstream, event, workspace))
    assert result.valid is True
    child_id, bound, timeout = workspace.calls[0]
    assert (child_id, timeout) == ("child-1", 17)
    binding, command = bound.split("\n", 1)
    encoded = shlex.split(binding)[1].split("=", 1)[1]
    assert json.loads(base64.b64decode(encoded)) == event["payload"]
    assert command == "verify-result"


def test_completion_contract_fails_fast_before_private_validator() -> None:
    workstream = {
        "required_evidence_fields": ["row_count"],
        "evidence_schema": {"row_count": {"type": "integer", "const": 11}},
        "allowed_files": [], "required_files": [],
        "validator_command": "must-not-run", "validator_timeout_sec": 17,
    }
    event = {"child_id": "child-1", "payload": {
        "evidence": {"row_count": 5}, "files": [],
    }}
    workspace = _Workspace()
    result = asyncio.run(validate_completion_contract(workstream, event, workspace))
    assert result.valid is False
    assert result.reason_codes == ("evidence_constraint_failed",)
    assert result.validator_exit_code is None
    assert workspace.calls == []


def test_database_authority_contract_rejects_unverified_or_wrong_finding() -> None:
    case = load_case(
        ROOT / "cases" / "mab-conflicting-specialist-results-5f19377089"
        / "public_case.yaml"
    ).raw
    workstream = next(
        item for item in case["delegation_workstreams"]
        if item["id"] == "requirement_worker_02"
    )
    assert "/app/output_data/event_receipt.json" in workstream["required_files"]
    assert workstream["evidence_schema"]["finding"]["const"] == "VACUUM"

    event = {"child_id": "authority", "payload": {
        "evidence": {
            "finding": "unable_to_verify",
            "report_path": "/app/output_data/workstreams/requirement_worker_02.json",
            "receipt_path": "/app/output_data/event_receipt.json",
            "receipt_sha256": "a" * 64,
            "revision_sha256": "1c3a50e63e7f8a6ba73633054c752f3f4623e4fd9c68f159a44e4c3bf7bd8385",
        },
        "files": [
            "/app/output_data/workstreams/requirement_worker_02.json",
            "/app/output_data/event_receipt.json",
        ],
    }}
    workspace = _Workspace()
    result = asyncio.run(validate_completion_contract(workstream, event, workspace))
    assert result.valid is False
    assert result.reason_codes == ("evidence_constraint_failed",)
    assert workspace.calls == []


def test_episode_start_exposes_only_structural_constraints() -> None:
    case = _case()
    start = _make_start(
        SimpleNamespace(
            episode_id="e", case_id=case["case_id"], execution_mode="async",
            agent_seed=1, guidance="none", use_container=True,
        ),
        case, {"instruction": "test"}, "container", "workspace-run",
    )
    public = start["workstream_contracts"]["wal_recovery"]
    assert public["evidence_schema"]["final_row_count"] == {"type": "integer"}
    encoded = json.dumps(start)
    assert "validator_command" not in encoded
    assert "result_kind" not in encoded


def test_public_enum_and_schema_are_forwarded_to_child_records() -> None:
    case = load_case(
        ROOT / "cases" / "distributed-model-runtime" / "public_case.yaml"
    ).raw
    start = _make_start(
        SimpleNamespace(
            episode_id="e", case_id=case["case_id"], execution_mode="async",
            agent_seed=1, guidance="none", use_container=True,
        ),
        case, {"instruction": "test"}, "container", "workspace-run",
    )
    assert start["workstream_contracts"]["select_backend"]["evidence_schema"][
        "recommended_backend"
    ]["enum"] == ["tensor", "pipeline", "data"]


def test_async_scheduler_returns_publicly_projectable_contract_rejection() -> None:
    case = _case()
    controller = DeliveryController("async", case)
    controller.on_spawn({"child_id": "authority"})
    controller.on_spawn({"child_id": "support"})
    event = {
        "child_id": "authority", "completion_id": "p",
        "result_kind": case["authoritative_result_kind"], "payload": {},
    }
    outcome = controller.on_complete(
        event, SimpleNamespace(valid=False, reason_codes=("evidence_constraint_failed",)),
    )[0]
    assert outcome["type"] == "result_rejected"
    assert outcome["reason_codes"] == ["evidence_constraint_failed"]
    assert "payload" not in outcome


def test_gateway_rejection_is_terminal_and_unconsumable() -> None:
    async def exercise() -> None:
        manager = object.__new__(SubagentManager)
        manager.children = {"child-1": ChildRecord(
            child_id="child-1", task="work", work_units=["ws"], targets=[],
            expected_output="out", priority="high", status="completed_hidden",
            completion_id="completion-1",
        )}
        manager.completion_to_child = {"completion-1": "child-1"}
        manager._delivery_event = asyncio.Event()
        # P0-8/9 rejection-feedback state, set as __init__ would on a real manager.
        manager.attempt_counts = Counter()
        manager.workstream_rejections = {}
        await manager.handle_rejection({
            "type": "result_rejected", "child_id": "child-1",
            "completion_id": "completion-1", "reason_codes": ["validator_command_failed"],
        })
        record = manager.children["child-1"]
        assert record.status == "contract_rejected"
        assert record.delivery is None
        assert manager.acknowledge("completion-1", "use", "try", "a1")["error"]

    asyncio.run(exercise())
