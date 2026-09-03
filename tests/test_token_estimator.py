"""Regression: the input estimator must count the *serialized* message payload.

The conservative estimate is the admission bound for strict budget admission
(spec §7.3).  Before the fix it only counted ``content`` and ``role``, so a
DeepSeek-style assistant message carrying ``reasoning_content`` plus
``tool_calls`` (whose ``arguments`` hold long serialized JSON, e.g. a terminal
command) was counted as a handful of tokens while the wire payload was tens of
thousands of characters.  Every field that is persisted and re-submitted on the
next call must be part of the estimate -- otherwise the pool settles to a usage
far above the reservation, records an overrun and halts a legitimately bounded
run.
"""
from __future__ import annotations

import json

from async_rbench.evaluation.budget import BudgetPool
from async_rbench.evaluation.model_backend import (
    conservative_input_estimate,
    exact_input_estimate,
    serialized_conversation_bytes,
)


def _assistant_with_reasoning_and_tool_call(
    reasoning_chars: int, arguments_chars: int,
) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "r" * reasoning_chars,
            "tool_calls": [{
                "id": "call-0",
                "type": "function",
                "function": {
                    "name": "terminal",
                    "arguments": json.dumps(
                        {"command": "c" * arguments_chars, "timeout_seconds": 30},
                    ),
                },
            }],
        },
    ]


_TOOL = [{
    "type": "function",
    "function": {
        "name": "terminal",
        "description": "Run a command.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
    },
}]


def test_conservative_estimate_covers_reasoning_content_and_tool_calls() -> None:
    """Repro: 10K reasoning + 10K tool-call arguments used to estimate ~17."""
    messages = _assistant_with_reasoning_and_tool_call(10_000, 10_000)
    estimate = conservative_input_estimate(messages, _TOOL)
    # The serialized payload alone is ~20K chars, so the bound must exceed it;
    # the pre-fix estimator reported 17 (role + content only).
    assert estimate >= 20_000
    # Old arithmetic counted only role + content: 9 chars.  The fix must have
    # looked at the actual serialized message, not the content string.
    old_style = len(messages[0].get("content") or "") + len(messages[0].get("role") or "")
    assert estimate > old_style * 2_000


def test_conservative_estimate_is_at_least_serialized_wire_bytes() -> None:
    """The bound is UTF-8 bytes of the exact serialized payload plus overhead."""
    messages = _assistant_with_reasoning_and_tool_call(777, 333)
    serialized = len(json.dumps(
        {"messages": messages, "tools": _TOOL}, ensure_ascii=False,
    ).encode("utf-8"))
    estimate = conservative_input_estimate(messages, _TOOL)
    assert estimate >= serialized
    assert estimate == serialized + 8 * len(messages) + 16 * len(_TOOL)
    assert serialized_conversation_bytes(messages, _TOOL) == serialized


def test_every_message_field_contributes_to_the_estimate() -> None:
    """role / content / reasoning_content / tool_calls / tool_call_id / name.

    Adding any one field must strictly increase the conservative bound: a
    field that stays uncounted is a field the pool silently under-reserves.
    """
    base: list[dict] = [{"role": "assistant", "content": "hello"}]
    assert conservative_input_estimate(base, []) > 0

    with_reasoning = [dict(base[0], reasoning_content="z" * 500)]
    assert conservative_input_estimate(with_reasoning, []) > conservative_input_estimate(base, [])

    with_call = [dict(base[0], tool_calls=[{
        "id": "call-1", "type": "function",
        "function": {"name": "terminal", "arguments": '{"a": "b"}'},
    }])]
    assert conservative_input_estimate(with_call, []) > conservative_input_estimate(base, [])

    tool_result_message = [{
        "role": "tool", "tool_call_id": "call-1", "content": '{"exit_code": 0, "output": "x"}',
    }]
    assert conservative_input_estimate(tool_result_message, []) > 0

    with_name = [{"role": "assistant", "name": "extra", "content": "y"}]
    assert conservative_input_estimate(with_name, []) > conservative_input_estimate(
        [{"role": "assistant", "content": "y"}], [],
    )

    with_list_content = [{"role": "assistant", "content": [{"type": "text", "text": "p" * 300}]}]
    assert conservative_input_estimate(with_list_content, []) > conservative_input_estimate(
        [{"role": "assistant", "content": ""}], [],
    )


def test_tool_schemas_are_counted() -> None:
    """The provider also tokenizes the tool definitions on every request."""
    plain = conservative_input_estimate([{"role": "user", "content": "hi"}], [])
    with_tools = conservative_input_estimate([{"role": "user", "content": "hi"}], _TOOL)
    assert with_tools > plain
    # Two copies of the same schema must roughly double the contribution.
    twice = conservative_input_estimate([{"role": "user", "content": "hi"}], _TOOL + _TOOL)
    assert twice > with_tools


def test_tokenizer_proxy_covers_the_serialized_payload_too() -> None:
    """The compact proxy also serializes the whole payload (it is a *proxy*).

    The old arithmetic counted only ``content``/``role`` (9 chars for this
    message), which collapses to ~15 tokens; the proxy must instead be derived
    from the serialized payload, whose ``chars // 4`` alone is ~2K.
    """
    messages = _assistant_with_reasoning_and_tool_call(4_000, 4_000)
    exact = exact_input_estimate(messages, _TOOL)
    assert exact >= 2_000  # about a quarter of the ~8.3K serialized payload
    # The proxy remains below the conservative bound (the relationship the
    # contract guarantees, spec §7.3).
    assert conservative_input_estimate(messages, _TOOL) >= exact


def test_exact_estimate_admission_then_settle_stays_within_budget() -> None:
    """A pool sized to the conservative estimate admits once and settles cleanly.

    This is the end-to-end guard for the estimator defect: with the old
    estimator the same call reserved ~17 tokens and then settled to the true
    usage, which recorded an overrun and halted the pool.
    """
    messages = _assistant_with_reasoning_and_tool_call(2_000, 2_000)

    async def exercise() -> None:
        estimate = conservative_input_estimate(messages, _TOOL)
        pool = BudgetPool("main_pre", maximum=estimate + 1_000)
        reservation = await pool.reserve(estimate, 1_000)
        assert reservation is not None
        overrun = await pool.settle(reservation.reservation_id, estimate + 500)
        assert overrun == 0
        assert pool.halted is False
        assert pool.settled == estimate + 500

    import asyncio

    asyncio.run(exercise())
