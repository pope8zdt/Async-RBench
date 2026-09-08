from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from ..contracts import FrameworkRequest, FrameworkResult, HarnessAction


def render_protocol_prompt(request: FrameworkRequest) -> str:
    payload = json.dumps(
        {"messages": request.messages, "tools": request.tools},
        ensure_ascii=False,
    )
    return (
        "You are running inside Async-RBench Track B. Choose only tools in the "
        "supplied schemas. Return one JSON object with `output_text` and `actions`; "
        "each action has `kind` equal to a supplied function name and an `arguments` "
        "object. Return an empty actions list when no tool is needed.\n\n"
        "TASK ENVIRONMENT: Benchmark terminal actions execute remotely in a Linux "
        "task container using bash. Use Linux paths and bash commands; task instructions "
        "usually name /app, but use the terminal tool with pwd to confirm the task "
        "working directory. The framework runtime workspace is separate; its current "
        "directory and host files are not the task workspace. Access task "
        "files only through the supplied benchmark tools, and wait for observations "
        "before treating an action as executed.\n\n"
        f"PUBLIC REQUEST JSON:\n{payload}"
    )


def _function_names(request: FrameworkRequest) -> set[str]:
    names: set[str] = set()
    for tool in request.tools:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if isinstance(function, Mapping) and function.get("name"):
            names.add(str(function["name"]))
    return names


def _protocol_payload(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        # Decode from each fence opening so literal backticks inside JSON strings
        # cannot prematurely terminate a command or answer. Recovery is allowed
        # only when there is one complete protocol object, never by block order.
        decoder = json.JSONDecoder()
        candidates: list[dict[str, Any]] = []
        for match in re.finditer(r"```(?:json\b)?\s*", candidate, re.IGNORECASE):
            body = candidate[match.end():]
            try:
                fenced_payload, end = decoder.raw_decode(body)
            except json.JSONDecodeError:
                continue
            if (
                body[end:].lstrip().startswith("```")
                and isinstance(fenced_payload, dict)
                and "actions" in fenced_payload
            ):
                candidates.append(fenced_payload)
        if len(candidates) > 1:
            raise ValueError("ambiguous framework protocol response: multiple JSON action objects")
        if candidates:
            return candidates[0]
    else:
        if isinstance(payload, dict) and "actions" in payload:
            return payload
    if re.search(r'"(?:output_text|actions)"\s*:', candidate):
        raise ValueError("malformed framework protocol response: expected one JSON action object")
    return None


def parse_protocol_result(
    text: str,
    request: FrameworkRequest,
    *,
    usage: Mapping[str, int] | None = None,
) -> FrameworkResult:
    payload = _protocol_payload(text)
    if payload is None:
        return FrameworkResult(output_text=text, usage=dict(usage or {}))
    raw_actions = payload["actions"]
    if not isinstance(raw_actions, list):
        raise ValueError("framework protocol actions must be a list")
    allowed = _function_names(request)
    actions: list[HarnessAction] = []
    for index, item in enumerate(raw_actions):
        if not isinstance(item, dict):
            raise ValueError(f"framework action {index} must be an object")
        kind = str(item.get("kind") or "")
        arguments = item.get("arguments", {})
        if kind not in allowed:
            raise ValueError(f"framework requested unavailable tool {kind!r}")
        if not isinstance(arguments, dict):
            raise ValueError(f"framework action {index} arguments must be an object")
        actions.append(HarnessAction(kind, arguments))
    output_text = str(payload.get("output_text") or "")
    return FrameworkResult(
        output_text=output_text,
        actions=tuple(actions),
        usage=dict(usage or {}),
        status=str(payload.get("status") or "completed"),
    )
