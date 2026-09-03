from __future__ import annotations

"""Task 10: end-to-end acceptance sequence and official-run hard gates.

Two halves:

* **Step 1 acceptance harness** — the ordered eight-scenario chain:

  1. a positive valid report submission is accepted and sealed;
  2. a missing report file blocks sealing with a public code the child can see;
  3. a malformed-JSON report blocks sealing the same way;
  4. a zero token budget ends the child terminal *without* a submission;
  5. a no-tool-call child ends as ``no_submission``, never as a rejection;
  6. after a public rejection exactly one recovery replacement is admitted and
     carries the prior rejection feedback;
  7. a second replacement for the same workstream is refused without starting a
     child or spending budget;
  8. a Linear and Async smoke run (three seeds each) shows nonzero child tokens,
     at least one main turn, no in-flight/private-only terminal rows, and
     complete mode-separated paper metrics.

* **Step 2 gate tests** — ``audit_run``, the ``audit-run`` CLI and official
  aggregation must return nonzero / hard-fail when: contract fixtures fail, a
  submission-stage validator lacks a public contract, a ``result_rejected``
  carries no actionable public code, a spawned child is still in flight when the
  episode closed, or an official Linear run has zero main tokens.  Development
  runs are reported but never trip the official hard gates.
"""

import asyncio
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

import async_rbench.evaluation.runner as runner_module
from async_rbench.evaluation.budget import BudgetPool
from async_rbench.evaluation.model_backend import ModelTurn, ToolCall
from async_rbench.evaluation.runner import EpisodeConfig, _make_start, run_episode
from async_rbench.evaluation.workspace_runtime import (
    CommandResult, DisabledWorkspaceRuntime,
)
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import (
    DeliveryReader, ProtocolEmitter,
)
from async_rbench.profiles.reference_scaffold_api.runtime import (
    ChildAgent, ChildRecord, ReferenceScaffold,
)
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


# ============================================================================
# Step 1 / scenarios 1-3: the Child pre-submit and seal gates share one public
# validation engine, so a bad report can never be sealed even when the Child
# skips ``validate_result``.
# ============================================================================

_REPORT_RECORD_ARGS = {
    "child_id": "child-1",
    "task": "produce report",
    "work_units": ["ws"],
    "targets": [],
    "expected_output": "report",
    "priority": "high",
    "required_evidence_fields": ["report_path", "finding", "revision_sha256"],
    "evidence_schema": {
        "report_path": {"type": "string"},
        "finding": {"type": "string"},
        "revision_sha256": {"type": "string"},
    },
    "allowed_result_files": ["/app/out.json"],
    "required_result_files": ["/app/out.json"],
    "public_result_contract": {
        "kind": "report_file",
        "report_file": {
            "path": "/app/out.json", "must_exist": True,
            "must_be_valid_json": True,
            "fields_equal_evidence": ["finding", "revision_sha256"],
        },
    },
    "result_file_contract_enforced": True,
}


class _SubmitOnFirstTurnBackend:
    """Turn 1 calls submit_result directly (skipping validate_result); later
    turns produce no tool call so the unsealed child ends on its own."""

    def __init__(self) -> None:
        self.turn = 0
        self.seen_tool_results: list[dict[str, Any]] = []
        self.submit_arguments: dict[str, Any] = {}

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}

    @staticmethod
    def _call(call_id: str, name: str, arguments: dict) -> ModelTurn:
        raw = [{"id": call_id, "type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments, sort_keys=True),
        }}]
        return ModelTurn(
            assistant_message={"role": "assistant", "content": None, "tool_calls": raw},
            tool_calls=[ToolCall(call_id, name, arguments)],
            total_tokens=7,
        )

    async def complete(self, **_: Any) -> ModelTurn:
        self.turn += 1
        for message in _.get("messages", []):
            if message.get("role") != "tool":
                continue
            content = message.get("content")
            if isinstance(content, str):
                try:
                    self.seen_tool_results.append(json.loads(content))
                except (json.JSONDecodeError, TypeError):
                    pass
        if self.turn == 1:
            self.submit_arguments = {
                "summary": "result",
                "result_kind_hint": "recovered",
                "evidence": {
                    "report_path": "/app/out.json",
                    "finding": "recovered",
                    "revision_sha256": "0" * 64,
                },
                "files": ["/app/out.json"],
            }
            return self._call("c-submit", "submit_result", self.submit_arguments)
        return ModelTurn(
            assistant_message={"role": "assistant", "content": "done"},
            tool_calls=[], total_tokens=1,
        )


class _AlwaysFailingReportWorkspace:
    """The rendered public report validator always fails the same way."""

    def __init__(self, output_line: str) -> None:
        self.output_line = output_line

    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult:
        return CommandResult(1, self.output_line)


class _AlwaysPassingReportWorkspace:
    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult:
        return CommandResult(0, "")


def _report_agent(workspace: Any, backend: Any) -> ChildAgent:
    config = ScaffoldConfig.from_file(
        None, {"backend": "scripted_test", "workspace_mode": "disabled"},
    )
    return ChildAgent(
        backend, workspace, config,
        ProtocolEmitter(stdout=io.StringIO()),
        BudgetPool("child_shared", maximum=500_000),
    )


def _report_record() -> ChildRecord:
    return ChildRecord(**_REPORT_RECORD_ARGS)


def _find_tool_result(seen: list[dict[str, Any]], key: str, code: str) -> dict[str, Any]:
    for result in seen:
        codes = result.get("reason_codes")
        if result.get(key) is not None and isinstance(codes, list) and code in codes:
            return result
    raise AssertionError(f"no tool result with {key} and code {code!r} in {seen}")


def test_acceptance_01_valid_report_submission_is_accepted() -> None:
    async def exercise() -> Any:
        agent = _report_agent(_AlwaysPassingReportWorkspace(), _SubmitOnFirstTurnBackend())
        return await agent.run(_report_record(), "test-model", 1), agent.backend

    outcome, backend = asyncio.run(exercise())
    assert outcome.kind == "submitted"
    assert outcome.payload is not None
    assert outcome.payload["evidence"]["finding"] == "recovered"
    assert outcome.hint == "recovered"


def test_acceptance_02_missing_report_file_blocks_sealing_with_public_code() -> None:
    async def exercise() -> Any:
        backend = _SubmitOnFirstTurnBackend()
        agent = _report_agent(_AlwaysFailingReportWorkspace(
            "ASYNC_RBENCH_CONTRACT_FAIL:report_file_missing\n",
        ), backend)
        return await agent.run(_report_record(), "test-model", 1), backend

    outcome, backend = asyncio.run(exercise())
    # A bad report cannot be sealed by submit_result even when the Child skipped
    # validate_result; the attempt ends without any submission.
    assert outcome.kind == "no_submission"
    result = _find_tool_result(backend.seen_tool_results, "sealed", "report_file_missing")
    assert result["sealed"] is False
    assert result["contract_part"] == "report_file"


def test_acceptance_03_malformed_json_report_blocks_sealing_with_public_code() -> None:
    async def exercise() -> Any:
        backend = _SubmitOnFirstTurnBackend()
        agent = _report_agent(_AlwaysFailingReportWorkspace(
            "ASYNC_RBENCH_CONTRACT_FAIL:report_json_invalid\n",
        ), backend)
        return await agent.run(_report_record(), "test-model", 1), backend

    outcome, backend = asyncio.run(exercise())
    assert outcome.kind == "no_submission"
    result = _find_tool_result(backend.seen_tool_results, "sealed", "report_json_invalid")
    assert result["sealed"] is False


# ============================================================================
# Step 1 / scenarios 4-5: non-submission ends are terminal and never fabricate a
# rejection.  A zero-budget pool and a no-tool-call child must each close the
# manager wait and Linear bundle with no child_completed / result_rejected.
# ============================================================================

class _NoToolBackend:
    async def complete(self, **_: Any) -> ModelTurn:
        return ModelTurn(
            assistant_message={"role": "assistant", "content": "not submitted"},
            tool_calls=[], total_tokens=7,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}


def _start(mode: str = "linear") -> dict[str, Any]:
    case_path = ROOT / "cases" / "data-recovery-service" / "public_case.yaml"
    case = load_case(case_path).raw
    task = yaml.safe_load(
        (case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8")
    )
    config = EpisodeConfig(
        episode_id="acceptance-lifecycle", case_id="data-recovery-service",
        execution_mode=mode, guidance="incentive", agent_seed=1,
        adapter_command=[sys.executable],
        output_dir=ROOT / "artifacts" / "test-unused", use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _scaffold(backend: Any) -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test", "workspace_mode": "disabled",
    })
    start = _start()
    only = start["initial_wave"][0]
    workstream_id = only["workstream_id"]
    start["initial_wave"] = [only]
    start["allowed_work_units"] = [workstream_id]
    start["workstream_contracts"] = {
        workstream_id: start["workstream_contracts"][workstream_id]
    }
    return ReferenceScaffold(
        start=start, config=config, backend=backend,
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
    )


async def _run_one_child(scaffold: ReferenceScaffold):
    manager = scaffold.manager
    manager._launch_queued = lambda: None
    manager.spawn_initial_wave()
    record = next(iter(manager.children.values()))
    await manager._run_child(record)
    return manager, record, scaffold.emitter.events


def test_acceptance_04_zero_token_budget_is_terminal_without_submission() -> None:
    async def exercise() -> Any:
        scaffold = _scaffold(_NoToolBackend())
        scaffold.manager.token_budget.maximum = 0
        return await _run_one_child(scaffold)

    manager, record, events = asyncio.run(exercise())
    assert record.status == "token_budget_exhausted"
    assert record.decision == "token_budget_exhausted"
    assert manager.unresolved_count() == 0
    assert manager.linear_bundle_ready() is True
    types = [event["type"] for event in events]
    assert "child_token_budget_exhausted" in types
    assert "child_completed" not in types
    assert "result_rejected" not in types


def test_acceptance_05_no_tool_call_ends_as_no_submission_not_rejection() -> None:
    manager, record, events = asyncio.run(_run_one_child(_scaffold(_NoToolBackend())))
    assert record.status == "no_submission"
    assert record.payload is None
    assert manager.unresolved_count() == 0
    types = [event["type"] for event in events]
    assert "child_no_submission" in types
    assert "child_completed" not in types
    assert "result_rejected" not in types
    assert "result_contract_validated" not in types


# ============================================================================
# Step 1 / scenarios 6-7: exactly one bounded recovery after a public rejection,
# and a second replacement refused without starting a child or spending budget.
# ============================================================================

_WAL_TASK = "retry wal recovery with a complete report artifact"


def _recovery_scaffold() -> ReferenceScaffold:
    start = _start()
    scaffold = ReferenceScaffold(
        start=start,
        config=ScaffoldConfig.from_file(
            None, {"backend": "scripted_test", "workspace_mode": "disabled"},
        ),
        backend=ScriptedTestBackend(),
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
    )
    manager = scaffold.manager
    for child_id, workstream_id in [
        ("c-wal", "wal_recovery"),
        ("c-check", "checkpoint_recovery"),
        ("c-merge", "merge_support"),
    ]:
        record = ChildRecord(
            child_id=child_id, task="t", work_units=[workstream_id], targets=[],
            expected_output="e", priority="normal", status="completed_hidden",
            completion_id=f"comp-{child_id}",
        )
        manager.children[child_id] = record
        manager.completion_to_child[f"comp-{child_id}"] = child_id
    for workstream_id in ("wal_recovery", "checkpoint_recovery", "merge_support"):
        manager.attempt_counts[workstream_id] = 1
    manager._launch_queued = lambda: None  # keep admitted children un-run
    return scaffold


def test_acceptance_06_07_one_recovery_admitted_with_feedback_then_second_refused() -> None:
    async def exercise() -> None:
        scaffold = _recovery_scaffold()
        manager = scaffold.manager
        await manager.handle_rejection({
            "completion_id": "comp-c-wal", "reason_codes": ["report_file_missing"],
            "child_id": "c-wal",
        })
        assert manager.workstream_rejections["wal_recovery"]["actionable"] is True
        pool = manager.token_budget

        # Scenario 6: the first replacement is admitted and carries feedback.
        first = await manager.spawn("wal_recovery", _WAL_TASK, [], "", "high")
        assert "child_id" in first, f"one recovery must be admitted: {first}"
        record = manager.children[first["child_id"]]
        assert record.attempt_number == 2
        assert record.prior_attempt_rejection["reason_codes"] == ["report_file_missing"]
        assert manager.recovery_spawn_counts["wal_recovery"] == 1
        messages = ChildAgent.initial_messages(record)
        payload = json.loads(messages[1]["content"])
        assert payload["prior_attempt"]["failed_attempt_count"] == 1
        assert payload["prior_attempt"]["last_rejection"]["reason_codes"] == ["report_file_missing"]
        reserved_after_first = pool.reserved
        assert reserved_after_first > 0

        # Scenario 7: a second replacement is refused and consumes nothing.
        before_count = len(manager.children)
        second = await manager.spawn("wal_recovery", _WAL_TASK + " v2", [], "", "high")
        assert "error" in second
        assert "maximum recovery attempts for workstream" in second["error"]
        assert second["budget_consumed"] is False
        assert len(manager.children) == before_count  # no child started
        assert pool.reserved == reserved_after_first  # nothing extra reserved
        assert manager.recovery_spawn_counts["wal_recovery"] == 1

    asyncio.run(exercise())


# ============================================================================
# Step 1 / scenario 8: Linear and Async smoke, three seeds each, checking the
# episode-level integrity facts and the mode-separated aggregate paper metrics.
# ============================================================================

@pytest.fixture(scope="module")
def smoke_scores(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict[str, Any]]]:
    root = tmp_path_factory.mktemp("acceptance-smoke")
    linear_config = root / "linear_config.yaml"
    linear_config.write_text("max_main_turns: 5\n", encoding="utf-8")

    def _build(episode_id: str, mode: str, seed: int) -> dict[str, Any]:
        monkey = pytest.MonkeyPatch()
        monkey.setattr(
            runner_module, "build_workspace_runtime",
            lambda start, config, event_asset_source_root=None: DisabledWorkspaceRuntime(),
        )
        adapter_command = [
            sys.executable,
            str(ROOT / "adapters" / "reference_scaffold_api.py"),
            "--backend", "scripted_test", "--workspace-mode", "disabled",
        ]
        if mode == "linear":
            adapter_command += ["--config", str(linear_config)]
        config = EpisodeConfig(
            episode_id=episode_id, case_id="data-recovery-service",
            execution_mode=mode, guidance="incentive", agent_seed=seed,
            adapter_command=adapter_command,
            output_dir=root / f"{mode}-{seed}", use_container=False,
            timeout_sec=60,
        )
        try:
            return asyncio.run(run_episode(ROOT, config))
        finally:
            monkey.undo()

    scores: dict[str, list[dict[str, Any]]] = {"linear": [], "async": []}
    for mode in ("linear", "async"):
        for seed in (1, 2, 3):
            scores[mode].append(_build(f"smoke-{mode}-{seed}", mode, seed))
    return scores


def _rows(score: dict[str, Any]) -> list[dict[str, Any]]:
    rows = score.get("child_terminal_classifications")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def test_acceptance_08_smoke_linear_and_async_three_seeds_each(smoke_scores: dict[str, list[dict[str, Any]]]) -> None:
    assert [score["execution_mode"] for score in smoke_scores["linear"]] == ["linear"] * 3
    assert [score["execution_mode"] for score in smoke_scores["async"]] == ["async"] * 3
    for mode, scores in smoke_scores.items():
        for score in scores:
            # Nonzero child tokens and at least one real main-side model turn.
            assert score["child_tokens"] > 0, f"{mode} {score['episode_id']} child tokens"
            assert int(score.get("main_tokens") or 0) > 0, (
                f"{mode} {score['episode_id']} main tokens"
            )
            rows = _rows(score)
            assert rows, f"{mode} {score['episode_id']} has no terminal classifications"
            assert len(rows) == 3, f"{mode} {score['episode_id']} spawned-child rows: {rows}"
            for row in rows:
                assert row["terminal_class"] != "in_flight"
                assert not (
                    row["terminal_class"] == "case_contract_failure"
                    and row.get("reason_codes") and not row.get("public_codes")
                ), "private-only rejection reached the scorer"
    # Mode-separated paper metrics are complete and identical in shape for the
    # two arms (each of the three episodes spawns three gateway-accepted children).
    from async_rbench.evaluation.aggregate import aggregate_reports

    records = smoke_scores["linear"] + smoke_scores["async"]
    audit = aggregate_reports(records, bootstrap_iterations=5)["audit"]
    assert audit["hard_fail"] is False
    report = aggregate_reports(records, bootstrap_iterations=5)
    paper = report["development_summary"]["paper_metrics_by_mode"]
    for mode in ("linear", "async"):
        metrics = paper[mode]
        assert metrics["gateway_accepted_count"] == 9
        assert metrics["sealed_submission_count"] == 9
        assert metrics["submission_acceptance_rate"] == 1.0
        assert metrics["terminal_class_counts"]["gateway_accepted"] == 9
        assert metrics["gateway_verdict_count"] == 9


# ============================================================================
# Step 2: audit_run and the audit-run CLI must return nonzero / hard-fail when a
# run root carries a private-only rejection, an in-flight child after close, or
# failing / hidden-submission contract fixtures.  Aggregate official runs must
# hard-fail on private-only rejections, unknown (in-flight) child terminals and
# zero-main-token Linear runs; development runs are reported but never gate.
# ============================================================================

_PASSING_FIXTURES = {
    "workstream_count": 0, "passed_count": 0, "failed_workstreams": [],
    "passed": True, "hidden_validator_workstream_count": 0,
    "note": "fixture audit stubbed", "workstreams": [],
}


def _write_episode(root: Path, episode_id: str, events: list[dict[str, Any]],
                   score: dict[str, Any] | None = None) -> None:
    episode_dir = root / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "episode_id": episode_id, "case_id": "secure-release",
        "instance_id": "seed-1", "execution_mode": "async",
        "score_status": "scored", "main_tokens": 50, "child_tokens": 30,
        "total_tokens": 80, "episode_duration_ms": 1.0,
        "result_contract_rejected_count": 0,
    }
    base.update(score or {})
    (episode_dir / "score.json").write_text(json.dumps(base), encoding="utf-8")
    (episode_dir / "event_source.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8",
    )


def _audit_run_with_stub_fixtures(root: Path, fixtures: dict[str, Any]) -> dict[str, Any]:
    from async_rbench.evaluation import audit
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(audit, "audit_contract_fixtures", lambda benchmark_root: fixtures)
    try:
        return audit.audit_run(root, ROOT)
    finally:
        monkeypatch.undo()


def test_gate_audit_run_flags_private_only_rejection() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_episode(root, "ep-priv", [
            {"type": "child_spawned", "child_id": "c1", "work_units": ["ws"]},
            {"type": "child_completed", "child_id": "c1", "completion_id": "k1",
             "payload": {"evidence": {"finding": "x"}}},
            {"type": "result_rejected", "child_id": "c1", "completion_id": "k1",
             "reason_codes": ["private_internal_evidence_failed"]},
            {"type": "episode_ended", "local_status": "completed"},
        ])
        report = _audit_run_with_stub_fixtures(root, _PASSING_FIXTURES)
        assert report["hard_fail"] is True
        assert "private_submission_rejection" in report["hard_fail_reasons"]
        assert report["child_terminal_integrity"]["episodes_with_private_only_rejection"] == ["ep-priv"]
        assert "contract_fixture_failure" not in report["hard_fail_reasons"]


def test_gate_audit_run_flags_inflight_child_after_episode_close() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_episode(root, "ep-inflight", [
            {"type": "child_spawned", "child_id": "c9", "work_units": ["ws"]},
            {"type": "episode_ended", "local_status": "completed"},
        ])
        report = _audit_run_with_stub_fixtures(root, _PASSING_FIXTURES)
        assert report["hard_fail"] is True
        assert "unknown_child_terminal" in report["hard_fail_reasons"]
        assert report["child_terminal_integrity"]["episodes_with_unknown_child_terminal"] == ["ep-inflight"]


def test_gate_audit_run_is_clean_for_well_formed_episodes() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_episode(root, "ep-clean", [
            {"type": "child_spawned", "child_id": "c1", "work_units": ["ws"]},
            {"type": "child_completed", "child_id": "c1", "completion_id": "k1",
             "payload": {"evidence": {"finding": "x"}}},
            {"type": "result_delivered", "child_id": "c1", "completion_id": "k1",
             "payload": {"evidence": {"finding": "x"}}},
            {"type": "episode_ended", "local_status": "completed"},
        ])
        report = _audit_run_with_stub_fixtures(root, _PASSING_FIXTURES)
        assert report["hard_fail"] is False
        assert report["hard_fail_reasons"] == []


def test_gate_audit_run_flags_failing_and_hidden_submission_fixtures() -> None:
    import tempfile

    failing = {
        "workstream_count": 1, "passed_count": 0,
        "failed_workstreams": ["secure-release/seed-1/ws"],
        "passed": False, "hidden_validator_workstream_count": 1,
        "note": "a submission-stage validator lacks a public contract", "workstreams": [],
    }
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_episode(root, "ep-clean", [
            {"type": "child_spawned", "child_id": "c1", "work_units": ["ws"]},
            {"type": "child_completed", "child_id": "c1", "completion_id": "k1",
             "payload": {"evidence": {"finding": "x"}}},
            {"type": "result_delivered", "child_id": "c1", "completion_id": "k1",
             "payload": {"evidence": {"finding": "x"}}},
            {"type": "episode_ended", "local_status": "completed"},
        ])
        report = _audit_run_with_stub_fixtures(root, failing)
        assert report["hard_fail"] is True
        assert "contract_fixture_failure" in report["hard_fail_reasons"]
        assert "hidden_submission_constraint" in report["hard_fail_reasons"]


def _fake_audit_report(reasons: list[str]) -> dict[str, Any]:
    return {
        "contract_fixtures": {
            "passed": True, "hidden_validator_workstream_count": 0,
        },
        "episode_count": 1,
        "artifact_compatibility": {"all_episodes_match_current": True},
        "resources": {"episodes": [{"case_id": "secure-release", "instance_id": "seed-1"}]},
        "hard_fail": bool(reasons),
        "hard_fail_reasons": reasons,
    }


def test_gate_audit_run_cli_returns_nonzero_on_hard_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import types

    import async_rbench.eval_cli as eval_cli
    monkeypatch.setattr(
        eval_cli, "audit_run",
        lambda root, benchmark_root: _fake_audit_report(["private_submission_rejection"]),
    )
    root = tmp_path / "run-root"
    root.mkdir()
    args = types.SimpleNamespace(
        root=str(root), output=str(tmp_path / "audit.json"),
    )
    assert eval_cli.cmd_audit_run(args) == 1


def test_gate_audit_run_cli_returns_zero_when_no_hard_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import types

    import async_rbench.eval_cli as eval_cli
    monkeypatch.setattr(
        eval_cli, "audit_run",
        lambda root, benchmark_root: _fake_audit_report([]),
    )
    root = tmp_path / "run-root"
    root.mkdir()
    args = types.SimpleNamespace(
        root=str(root), output=str(tmp_path / "audit.json"),
    )
    assert eval_cli.cmd_audit_run(args) == 0


# --- aggregate official hard gates -------------------------------------------


def _agg_record(
    rows: list[dict[str, Any]], *, mode: str = "async", official: bool = False,
    main_tokens: int = 100,
) -> dict[str, Any]:
    return {
        "episode_id": f"case-a-{mode}-{int(official)}", "case_id": "case-a",
        "instance_id": "seed-1", "repeat": 0, "execution_mode": mode,
        "guidance": "incentive", "adapter_profile": "reference_scaffold_api",
        "runtime_mode": "api_only", "score_status": "scored",
        "test_point_pass_rate": 0.9, "scenario_constructed": True,
        "denominator_digest": "digest-a", "total_tokens": 100,
        "main_tokens": main_tokens,
        "leaderboard_eligible": official, "conformance_passed": official,
        "capability_categories": ["stale_result_rejection"],
        "split": "test" if official else "calibration",
        "model": "deepseek-v4-pro",
        "scaffold_and_protocol_sha256": "evaluator-scaffold-v1",
        "semantic_task_score": 0.9,
        "dynamic_control_score": 0.9 if mode == "async" else None,
        "dt_score": 0.9 if mode == "async" else None,
        "score_policy_version": SCORE_POLICY_VERSION,
        "child_terminal_classifications": rows,
    }


def _cls_row(
    child: str, cls: str, *, attempt: int = 1, tokens: int = 10,
    reason_codes: list[str] | None = None,
    public_codes: list[str] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "child_id": child, "workstream_id": "ws-a", "attempt_number": attempt,
        "retry": attempt >= 2, "terminal_class": cls,
        "sealed_submission": cls in {"gateway_accepted", "public_rejection"},
        "gateway_verdict": cls in {"gateway_accepted", "public_rejection"},
        "consumed_by_main": False, "tokens": tokens,
    }
    if reason_codes is not None:
        row["reason_codes"] = reason_codes
    if public_codes is not None:
        row["public_codes"] = public_codes
    return row


def test_gate_aggregate_unknown_child_terminal_hard_fails_official_only() -> None:
    from async_rbench.evaluation.aggregate import aggregate_reports

    official_bad = _agg_record([_cls_row("c1", "in_flight")], official=True)
    audit = aggregate_reports([official_bad], bootstrap_iterations=5)["audit"]
    assert audit["unknown_child_terminal_count"] == 1
    assert audit["hard_fail"] is True
    assert "unknown_child_terminal" in audit["hard_fail_reasons"]

    # The same signature on a development run is reported but never gates.
    dev = _agg_record([_cls_row("c1", "in_flight")], official=False)
    dev_audit = aggregate_reports([dev], bootstrap_iterations=5)["audit"]
    assert dev_audit["unknown_child_terminal_count"] == 1
    assert dev_audit["hard_fail"] is False
    assert "unknown_child_terminal" not in dev_audit["hard_fail_reasons"]


def test_gate_aggregate_private_submission_rejection_hard_fails_official_only() -> None:
    from async_rbench.evaluation.aggregate import aggregate_reports

    row = _cls_row(
        "c1", "case_contract_failure", reason_codes=["private_internal_evidence_failed"],
    )
    official_bad = _agg_record([row], official=True)
    audit = aggregate_reports([official_bad], bootstrap_iterations=5)["audit"]
    assert audit["private_submission_rejection_count"] == 1
    assert audit["hard_fail"] is True
    assert "private_submission_rejection" in audit["hard_fail_reasons"]

    dev = _agg_record([dict(row)], official=False)
    dev_audit = aggregate_reports([dev], bootstrap_iterations=5)["audit"]
    assert dev_audit["private_submission_rejection_count"] == 1
    assert dev_audit["hard_fail"] is False


def test_gate_aggregate_clean_official_run_has_no_terminal_integrity_reasons() -> None:
    from async_rbench.evaluation.aggregate import aggregate_reports

    clean = _agg_record(
        [_cls_row("c1", "gateway_accepted"), _cls_row("c2", "gateway_accepted")],
        official=True, mode="linear",
    )
    audit = aggregate_reports([clean], bootstrap_iterations=5)["audit"]
    assert audit["hard_fail"] is False
    assert audit["hard_fail_reasons"] == []
