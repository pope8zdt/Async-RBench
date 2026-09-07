from __future__ import annotations

import json
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
        f"PUBLIC REQUEST JSON:\n{payload}"
    )


def _function_names(request: FrameworkRequest) -> set[str]:
    names: set[str] = set()
    for tool in request.tools:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if isinstance(function, Mapping) and function.get("name"):
            names.add(str(function["name"]))
    return names


def parse_protocol_result(
    text: str,
    request: FrameworkRequest,
    *,
    usage: Mapping[str, int] | None = None,
) -> FrameworkResult:
    candidate = text.strip()
    if candidate.startswith("```json") and candidate.endswith("```"):
        candidate = candidate[7:-3].strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return FrameworkResult(output_text=text, usage=dict(usage or {}))
    if not isinstance(payload, dict) or "actions" not in payload:
        return FrameworkResult(output_text=text, usage=dict(usage or {}))
    allowed = _function_names(request)
    actions: list[HarnessAction] = []
    for index, item in enumerate(payload.get("actions") or []):
        if not isinstance(item, dict):
            raise ValueError(f"framework action {index} must be an object")
        kind = str(item.get("kind") or "")
        arguments = item.get("arguments") or {}
        if kind not in allowed:
            raise ValueError(f"framework requested unavailable tool {kind!r}")
        if not isinstance(arguments, dict):
            raise ValueError(f"framework action {index} arguments must be an object")
        actions.append(HarnessAction(kind, arguments))
    return FrameworkResult(
        output_text=str(payload.get("output_text") or ""),
        actions=tuple(actions),
        usage=dict(usage or {}),
        status=str(payload.get("status") or "completed"),
    )
