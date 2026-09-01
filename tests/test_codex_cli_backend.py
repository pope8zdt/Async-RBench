from __future__ import annotations

import json

from async_rbench.evaluation.model_backend import (
    CodexCLIBackend,
    _codex_cli_output_schema,
    _parse_codex_cli_jsonl,
    build_backend,
)
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig


def test_codex_cli_config_and_backend_selection() -> None:
    config = ScaffoldConfig(
        backend="codex_cli",
        api_key_required=False,
        main_model="gpt-5.6-sol",
        child_model="gpt-5.6-sol",
    )
    config.validate()
    assert isinstance(build_backend(config), CodexCLIBackend)


def test_codex_cli_schema_limits_tool_names() -> None:
    schema = _codex_cli_output_schema([
        {"type": "function", "function": {
            "name": "terminal",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["command"],
            },
        }},
        {"type": "function", "function": {
            "name": "finish",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }},
    ])
    branches = schema["properties"]["tool_calls"]["items"]["anyOf"]
    assert [branch["properties"]["name"]["enum"][0] for branch in branches] == [
        "terminal", "finish",
    ]
    terminal = branches[0]
    assert terminal["required"] == ["id", "name", "arguments"]
    assert terminal["properties"]["arguments"]["additionalProperties"] is False
    assert "anyOf" in terminal["properties"]["arguments"]["properties"]["timeout"]


def test_parse_codex_cli_jsonl_uses_final_message_and_usage() -> None:
    payload = {"content": "", "tool_calls": [
        {"id": "call-1", "name": "terminal", "arguments": {"command": "pwd"}}
    ]}
    stdout = "\n".join([
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "old"}}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(payload)}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 11, "output_tokens": 7}}),
    ])
    parsed, tokens = _parse_codex_cli_jsonl(stdout)
    assert parsed == payload
    assert tokens == 18


def test_codex_cli_prompt_contains_only_supplied_conversation() -> None:
    prompt = CodexCLIBackend._prompt(
        "main", [{"role": "user", "content": "task"}],
        [{"type": "function", "function": {"name": "finish"}}], 17,
    )
    assert '"deterministic_seed_label": 17' in prompt
    assert '"content": "task"' in prompt
    assert "Do not use shell, filesystem, web, MCP" in prompt
