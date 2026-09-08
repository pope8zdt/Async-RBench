from __future__ import annotations

import json

import pytest

from async_rbench.track_b.contracts import FrameworkRequest
from async_rbench.track_b.frameworks.common import parse_protocol_result


def _request() -> FrameworkRequest:
    return FrameworkRequest(
        messages=(),
        tools=({"type": "function", "function": {"name": "terminal"}},),
    )


def _action_text(command: str = "ls -la /app") -> str:
    return json.dumps({
        "output_text": "Inspecting the workspace.",
        "actions": [{"kind": "terminal", "arguments": {"command": command}}],
    })


def test_recovers_single_corrected_json_block_from_real_failure_shape() -> None:
    # The live dependency child emitted malformed JSON, then corrected it in a
    # second fence. Neither the malformed attempt nor the explanation is an action.
    text = (
        '```json\n{"output_text":"Inspecting the workspace.","actions":'
        '[{"kind":"terminal","arguments":{"command":"ls -la /app" responses: []}}]}\n'
        '```Wait, I need valid JSON format for the tool call.\n'
        "Let's construct the response properly.\n```json\n"
        + _action_text() + "\n```"
    )

    result = parse_protocol_result(text, _request(), usage={"output_tokens": 1718})

    assert len(result.actions) == 1
    assert result.actions[0].kind == "terminal"
    assert result.actions[0].arguments == {"command": "ls -la /app"}
    assert result.output_text == "Inspecting the workspace."
    assert result.usage == {"output_tokens": 1718}


def test_rejects_multiple_valid_protocol_blocks_without_selecting_an_action() -> None:
    text = f"```json\n{_action_text('first')}\n```\nCorrection:\n```json\n{_action_text('second')}\n```"

    with pytest.raises(ValueError, match="ambiguous"):
        parse_protocol_result(text, _request())


@pytest.mark.parametrize("text", [
    '{"output_text":"checking","actions":[',
    '```json\n{"output_text":"checking","actions":[}\n```',
    '{"output_text":"checking"}',
    'Here is my action: {"actions":[]}',
])
def test_malformed_protocol_is_not_silently_accepted_as_a_final_answer(text: str) -> None:
    with pytest.raises(ValueError, match="protocol"):
        parse_protocol_result(text, _request())


@pytest.mark.parametrize("actions", [None, False, 0, {}, ""])
def test_actions_must_be_a_list_even_when_the_value_is_falsey(actions) -> None:
    text = json.dumps({"output_text": "checking", "actions": actions})

    with pytest.raises(ValueError, match="actions must be a list"):
        parse_protocol_result(text, _request())


@pytest.mark.parametrize("arguments", [None, False, 0, [], ""])
def test_explicit_action_arguments_must_be_an_object(arguments) -> None:
    text = json.dumps({"actions": [{"kind": "terminal", "arguments": arguments}]})

    with pytest.raises(ValueError, match="arguments must be an object"):
        parse_protocol_result(text, _request())


def test_recovered_action_still_obeys_tool_allowlist() -> None:
    text = 'Corrected response:\n```json\n{"actions":[{"kind":"unavailable","arguments":{}}]}\n```'

    with pytest.raises(ValueError, match="unavailable tool"):
        parse_protocol_result(text, _request())


def test_fenced_terminal_command_can_contain_literal_markdown_fences() -> None:
    command = "printf '```json\\n{}\\n```'"
    result = parse_protocol_result(f"```json\n{_action_text(command)}\n```", _request())

    assert result.actions[0].arguments == {"command": command}


@pytest.mark.parametrize("text", ["agents result", "graph result", '{"answer":"done"}'])
def test_plain_final_answers_keep_compatibility(text: str) -> None:
    result = parse_protocol_result(text, _request(), usage={"input_tokens": 7})

    assert result.output_text == text
    assert result.actions == ()
    assert result.usage == {"input_tokens": 7}


def test_blank_protocol_answer_is_preserved_for_scaffold_termination_classification() -> None:
    result = parse_protocol_result(
        '{"output_text":"\\n","actions":[]}',
        _request(),
        usage={"input_tokens": 11, "output_tokens": 2},
    )

    assert result.output_text == "\n"
    assert result.actions == ()
    assert result.status == "completed"
    assert result.usage == {"input_tokens": 11, "output_tokens": 2}


def test_explicit_nonempty_final_answer_without_actions_is_allowed() -> None:
    result = parse_protocol_result('{"output_text":"done","actions":[]}', _request())

    assert result.output_text == "done"
    assert result.actions == ()
