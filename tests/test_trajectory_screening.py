from __future__ import annotations

import json
import os
import asyncio
from pathlib import Path

from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.evaluation.model_backend import ModelTurn, ToolCall
from async_rbench.trajectory_curation import trajectory_review_record
from async_rbench.trajectory_screening import (
    decision_records,
    load_key_for_config,
    model_screen,
    normalize_mini,
    normalize_openhands,
    normalize_terminus,
    normalize_swe_agent, normalize_tensorblock, normalize_terminal_session, render_screening_workspace,
    rule_screen,
    validate_coarse_label,
)


def test_swe_agent_and_terminal_fallbacks_preserve_roles_without_inventing_reasoning() -> None:
    steps, metadata = normalize_swe_agent({
        "environment": "swe_main",
        "trajectory": [{"thought": "inspect", "action": "open a.py", "observation": "line 1"}],
    })
    assert [step["role"] for step in steps] == ["agent", "environment"]
    assert metadata["environment"] == "swe_main"
    terminal_steps, terminal_metadata = normalize_terminal_session(
        "root@host:/app# setup\nfailed\nroot@host:/app# run\nerror\n",
        {"instruction": "solve it"},
    )
    assert terminal_steps[0]["kind"] == "task"
    assert all(step["role"] == "environment" for step in terminal_steps[1:])
    assert terminal_metadata["trajectory_format"].endswith("without_reasoning_trace")


def _normalized(steps: list[dict]) -> dict:
    return {
        "schema_version": "1", "review_id": "review-1", "task_name": "task-a",
        "manifest_solved": False, "result": {}, "steps": steps,
    }


def test_normalize_mini_keeps_task_action_and_observation() -> None:
    steps, _ = normalize_mini({"messages": [
        {"role": "system", "content": "hidden system prompt"},
        {"role": "user", "content": "repair the data"},
        {"role": "assistant", "content": "THOUGHT: inspect\n```bash\nls -la\n```"},
        {"role": "tool", "content": "missing file"},
    ]})
    assert [step["kind"] for step in steps] == ["task", "action", "observation"]
    assert steps[1]["command"] == "ls -la"
    assert "hidden system prompt" not in json.dumps(steps)


def test_normalize_openhands_preserves_original_event_ids() -> None:
    steps, _ = normalize_openhands([
        {"id": 0, "source": "agent", "action": "system", "message": "system"},
        {"id": 2, "source": "user", "action": "message", "content": "do it"},
        {"id": 5, "source": "agent", "action": "run", "args": {"command": "ls"}},
        {"id": 6, "source": "agent", "observation": "run", "content": "not found",
         "metadata": {"exit_code": 1}},
    ])
    assert [step["step_id"] for step in steps] == [2, 5, 6]
    assert steps[1]["command"] == "ls"
    assert steps[2]["exit_code"] == 1


def test_normalize_tensorblock_deduplicates_accumulated_tool_history() -> None:
    first = {
        "messages": [
            {"role": "system", "content": "hidden"},
            {"role": "user", "content": [{"type": "text", "text": "fix issue"}]},
        ],
        "response": {"choices": [{"message": {"content": None, "tool_calls": [{
            "id": "call-1", "function": {"name": "execute_bash", "arguments": '{"command":"ls"}'},
        }]}}]},
    }
    second = {
        "messages": first["messages"] + [
            {"role": "assistant", "content": None, "tool_calls": first["response"]["choices"][0]["message"]["tool_calls"]},
            {"role": "tool", "tool_call_id": "call-1", "content": "file.py"},
        ],
        "response": {"choices": [{"message": {"content": "done", "tool_calls": []}}]},
    }
    steps, metadata = normalize_tensorblock([first, second], {})
    assert [step["kind"] for step in steps] == ["task", "action", "observation", "final"]
    assert sum(step.get("content") == "file.py" for step in steps) == 1
    assert steps[1]["command"].startswith("execute_bash")
    assert metadata["instruction"] == "fix issue"
    assert metadata["trajectory_format"].endswith("without_reasoning")


def test_normalize_terminus_builds_stable_episode_step_ids() -> None:
    steps, meta = normalize_terminus([
        {"episode": 0, "prompt": "large first prompt", "response": json.dumps({
            "analysis": "inspect", "commands": [{"command": "ls"}], "task_complete": False,
        })},
        {"episode": 1, "prompt": "New Terminal Output:\nfailed: missing", "response": json.dumps({
            "plan": "recover instead", "commands": [{"command": "restore"}], "task_complete": True,
        })},
    ], {"instruction": "recover files"})
    assert [step["step_id"] for step in steps] == [0, 2, 3, 4]
    assert steps[-1]["kind"] == "final"
    assert meta["instruction"] == "recover files"


def test_rule_screen_produces_evidence_grounded_decision_template() -> None:
    normalized = _normalized([
        {"step_id": 1, "kind": "task", "role": "user", "content": "recover"},
        {"step_id": 2, "kind": "action", "role": "agent", "content": "inspect"},
        {"step_id": 3, "kind": "observation", "role": "environment", "content": "error: file not found"},
        {"step_id": 4, "kind": "action", "role": "agent", "content": "recover and verify instead"},
        {"step_id": 5, "kind": "observation", "role": "environment", "content": "restored"},
        {"step_id": 6, "kind": "final", "role": "agent", "content": "done"},
    ])
    label = rule_screen(normalized)
    assert validate_coarse_label(label, normalized) == []
    assert label["candidate_decisions"][0]["trigger_step_ids"] == [3]
    review = trajectory_review_record({"traj_id": "review-1", "task_name": "task-a"})
    rows = decision_records(review, label)
    assert rows[0]["agent_proposal"]["response_step_ids"] == [4]
    assert rows[0]["human_review"]["benchmark_eligible"] == "pending"


def test_coarse_validation_rejects_nonexistent_evidence() -> None:
    normalized = _normalized([
        {"step_id": 1, "kind": "task", "role": "user", "content": "recover"},
    ])
    label = rule_screen(normalized)
    label["candidate_decisions"] = [{
        "decision_id": "review-1:d1", "event_type": "reverification",
        "trigger_step_ids": [99], "precondition_step_ids": [], "response_step_ids": [1],
        "consequence_step_ids": [], "affected_scope": "local_branch",
        "topology_roles": ["validation_branch"],
        "suggested_capability_target": "async_dynamic_replanning",
        "suggested_relevance_tier": "direct", "counterfactual_failure": "bad", "rationale": "test",
    }]
    assert any("existing integer step ids" in error for error in validate_coarse_label(label, normalized))


def test_key_file_mapping_does_not_put_secret_in_artifacts(tmp_path: Path) -> None:
    config = ScaffoldConfig(
        main_model="qwen", child_model="qwen", api_key_env="ASYNC_RBENCH_TEST_QWEN_KEY",
    )
    key_file = tmp_path / "apikey.txt"
    key_file.write_text("my-qwen=secret-test-value\n", encoding="utf-8")
    try:
        source = load_key_for_config(config, key_file, "my-qwen")
        assert source == "key-file:my-qwen"
        assert os.environ[config.api_key_env] == "secret-test-value"
    finally:
        os.environ.pop(config.api_key_env, None)


def test_model_screen_uses_structured_evidence_contract(monkeypatch) -> None:
    normalized = _normalized([
        {"step_id": 1, "kind": "action", "role": "agent", "content": "start provisional work"},
        {"step_id": 2, "kind": "observation", "role": "environment", "content": "late result"},
        {"step_id": 3, "kind": "action", "role": "agent", "content": "verify again"},
    ])
    arguments = {
        "review_id": "review-1", "trajectory_quality": "usable",
        "failure_attribution": "model", "replanning_evidence": "indirect",
        "research_events": ["reverification"], "summary": "A candidate transition.",
        "candidate_decisions": [{
            "decision_id": "review-1:d1", "event_type": "reverification",
            "trigger_step_ids": [2], "precondition_step_ids": [1], "response_step_ids": [3],
            "consequence_step_ids": [], "affected_scope": "local_branch",
            "topology_roles": ["validation_branch"],
            "suggested_capability_target": "async_dynamic_replanning",
            "suggested_relevance_tier": "direct",
            "async_result_convertible": True, "arrival_order_matters": True,
            "plan_change_required": True, "ordinary_sequential_failure": False,
            "transformation_mode": "externalized_sequential_boundary",
            "source_event_observed": False, "source_semantics_preserved": True,
            "independent_source_design": "A child independently observes the late result.",
            "evidence_confidence": "high", "counterfactual_failure": "stale plan",
            "rationale": "steps 1 and 2",
        }],
    }

    class Backend:
        async def complete(self, **_kwargs):
            return ModelTurn(
                assistant_message={"role": "assistant", "content": None},
                tool_calls=[ToolCall("call-1", "submit_trajectory_screen", arguments)],
                total_tokens=123,
            )

    monkeypatch.setattr("async_rbench.trajectory_screening.build_backend", lambda _config: Backend())
    config = ScaffoldConfig(main_model="qwen", child_model="qwen", api_key_required=False)
    label, tokens = asyncio.run(model_screen(normalized, config))
    assert tokens == 123
    assert label["screening_mode"] == "model"
    assert validate_coarse_label(label, normalized) == []


def test_workspace_renders_trace_coarse_label_and_human_choices(tmp_path: Path) -> None:
    review = trajectory_review_record({
        "traj_id": "review-1", "task_name": "task-a", "agent": "mini",
        "model": "model-a", "solved": False, "step_count": 6,
    })
    normalized = _normalized([
        {"step_id": 1, "kind": "task", "role": "user", "content": "recover"},
        {"step_id": 2, "kind": "action", "role": "agent", "content": "inspect"},
    ])
    label = rule_screen(normalized)
    output = tmp_path / "workspace.html"
    render_screening_workspace([review], [normalized], [label], [], output)
    text = output.read_text(encoding="utf-8")
    assert "轨迹阅读与粗标复核" in text
    assert "Agent 粗标" in text
    assert "导出决策复核" in text
