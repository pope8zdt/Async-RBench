from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
import urllib.error
import urllib.request
import threading
from dataclasses import dataclass
from typing import Any, Protocol


class ProviderConfig(Protocol):
    """Provider-facing config surface the kernel model backend reads.

    A participant profile's config (e.g. ``ScaffoldConfig``) satisfies this
    structurally, so the kernel backend never imports profile code.
    """

    backend: str
    api_url: str
    max_api_concurrency: int
    max_tokens_parameter: str
    max_output_tokens: int
    send_seed: bool
    temperature: float | None
    request_body_extra: dict[str, Any]
    extra_headers: dict[str, str]
    request_timeout_sec: int
    codex_executable: str
    codex_reasoning_effort: str

    def api_key(self) -> str: ...


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelTurn:
    assistant_message: dict[str, Any]
    tool_calls: list[ToolCall]
    total_tokens: int = 0
    resolved_model: str = ""
    system_fingerprint: str | None = None


class ModelBackend(Protocol):
    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        seed: int,
    ) -> ModelTurn: ...


class OpenAICompatibleBackend:
    """Small dependency-free Chat Completions tool-calling backend."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_api_concurrency)
        self._observation_lock = threading.Lock()
        self._observations: set[tuple[str, str, str, str | None]] = set()

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        seed: int,
    ) -> ModelTurn:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            self.config.max_tokens_parameter: self.config.max_output_tokens,
        }
        if self.config.send_seed:
            payload["seed"] = seed
        if self.config.temperature is not None:
            payload["temperature"] = self.config.temperature
        payload.update(self.config.request_body_extra)
        async with self._semaphore:
            return await asyncio.to_thread(self._request, payload, role)

    def _request(self, payload: dict[str, Any], role: str) -> ModelTurn:
        headers = {
            "Content-Type": "application/json",
        }
        api_key = self.config.api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers.update(self.config.extra_headers)
        request = urllib.request.Request(
            self.config.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout_sec) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Never dump the full request payload (messages can contain the task
            # prompt and the participant's own reasoning) to a shared file: it
            # leaks prompt content and is overwritten/contaminated across
            # episodes.  Only the provider's error detail is surfaced in memory.
            detail = exc.read().decode("utf-8", errors="replace")[-4000:]
            raise RuntimeError(f"model API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"model API request failed: {exc}") from exc
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected model API response: {str(body)[:2000]}") from exc
        calls: list[ToolCall] = []
        for index, item in enumerate(message.get("tool_calls") or []):
            function = item.get("function", {})
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                arguments = {"_malformed_arguments": raw_arguments}
            calls.append(ToolCall(
                id=str(item.get("id") or f"call-{index}"),
                name=str(function.get("name") or ""),
                arguments=arguments if isinstance(arguments, dict) else {"value": arguments},
            ))
        usage = body.get("usage") or {}
        resolved_model = str(body.get("model") or "")
        fingerprint = body.get("system_fingerprint")
        # Echo the assistant tool calls into the next turn's message history.
        # Some relays (e.g. Gemini via OCI) omit the client-facing tool-call
        # ``id``; OpenAI-compatible tool history requires it on every entry and
        # rejects the follow-up request with ``toolCalls[0].id`` missing. Inject
        # the same ``call-{index}`` fallback used for ``ToolCall`` so the echoed
        # assistant ``tool_calls`` match the ``tool_call_id`` of the tool
        # result messages produced by ``_tool_result``.
        sanitized_tool_calls: list[dict[str, Any]] = []
        for index, item in enumerate(message.get("tool_calls") or []):
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            if not entry.get("id"):
                entry["id"] = f"call-{index}"
            sanitized_tool_calls.append(entry)
        with self._observation_lock:
            self._observations.add((role.split(":", 1)[0], str(payload["model"]), resolved_model, fingerprint))
        return ModelTurn(
            assistant_message={
                "role": "assistant",
                "content": message.get("content"),
                **({"reasoning_content": message["reasoning_content"]}
                   if message.get("reasoning_content") is not None else {}),
                **({"tool_calls": sanitized_tool_calls} if sanitized_tool_calls else {}),
            },
            tool_calls=calls,
            total_tokens=int(usage.get("total_tokens") or 0),
            resolved_model=resolved_model,
            system_fingerprint=fingerprint,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        with self._observation_lock:
            observations = sorted(self._observations, key=lambda item: tuple(str(x) for x in item))
        return {
            "model_observations": [
                {
                    "role": role,
                    "requested_model": requested,
                    "resolved_model": resolved,
                    "system_fingerprint": fingerprint,
                }
                for role, requested, resolved, fingerprint in observations
            ]
        }


def _parse_codex_cli_jsonl(stdout: str) -> tuple[dict[str, Any], int]:
    """Extract the final structured answer and token count from ``codex exec``."""
    messages: list[str] = []
    usage: dict[str, Any] = {}
    for raw in stdout.splitlines():
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                messages.append(str(item.get("text") or ""))
        elif event.get("type") == "turn.completed":
            usage = dict(event.get("usage") or {})
    if not messages:
        raise RuntimeError("Codex CLI output did not contain an agent message")
    try:
        payload = json.loads(messages[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Codex CLI final message was not valid structured JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Codex CLI final message must be a JSON object")
    total = int(usage.get("total_tokens") or 0)
    if not total:
        total = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
    return payload, total


def _strict_codex_property(spec: dict[str, Any], *, required: bool) -> dict[str, Any]:
    """Translate a function argument schema to the strict response-schema subset."""
    value_type = str(spec.get("type") or "string")
    description = str(spec.get("description") or "")
    if value_type == "object":
        properties = dict(spec.get("properties") or {})
        if not properties:
            normalized: dict[str, Any] = {
                "type": "string",
                "description": (description + " Return this object as a JSON-encoded string.").strip(),
            }
        else:
            originally_required = set(spec.get("required") or [])
            normalized = {
                "type": "object",
                "properties": {
                    name: _strict_codex_property(
                        dict(child), required=name in originally_required,
                    )
                    for name, child in properties.items()
                },
                "required": list(properties),
                "additionalProperties": False,
            }
            if description:
                normalized["description"] = description
    elif value_type == "array":
        normalized = {
            "type": "array",
            "items": _strict_codex_property(dict(spec.get("items") or {}), required=True),
        }
        if description:
            normalized["description"] = description
    else:
        normalized = {"type": value_type}
        for key in ("description", "enum", "minimum", "maximum", "minLength", "maxLength"):
            if key in spec:
                normalized[key] = spec[key]
    if required:
        return normalized
    return {"anyOf": [normalized, {"type": "null"}]}


def _codex_cli_output_schema(tools: list[dict[str, Any]]) -> dict[str, Any]:
    branches: list[dict[str, Any]] = []
    for tool in tools:
        function = dict(tool.get("function") or {})
        name = str(function.get("name") or "")
        if not name:
            continue
        parameters = dict(function.get("parameters") or {})
        properties = dict(parameters.get("properties") or {})
        required = set(parameters.get("required") or [])
        branches.append({
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string", "enum": [name]},
                "arguments": {
                    "type": "object",
                    "properties": {
                        key: _strict_codex_property(dict(value), required=key in required)
                        for key, value in properties.items()
                    },
                    "required": list(properties),
                    "additionalProperties": False,
                },
            },
            "required": ["id", "name", "arguments"],
            "additionalProperties": False,
        })
    item_schema: dict[str, Any] = (
        {"anyOf": branches}
        if branches else {
            "type": "object", "properties": {}, "required": [],
            "additionalProperties": False,
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "tool_calls": {
                "type": "array",
                "items": item_schema,
            },
        },
        "required": ["content", "tool_calls"],
        "additionalProperties": False,
    }


class CodexCLIBackend:
    """Use the locally authenticated Codex CLI as a structured tool-call backend.

    Every turn is stateless and receives the complete model-visible message history.
    The CLI runs ephemerally in a fresh empty directory with a read-only sandbox, so
    it cannot inspect the benchmark repository or private evaluator artifacts.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_api_concurrency)
        self._observation_lock = threading.Lock()
        self._observations: set[tuple[str, str, str, str | None]] = set()

    @staticmethod
    def _prompt(
        role: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], seed: int,
    ) -> str:
        return (
            "You are the model backend inside an Async-RBench reference scaffold. "
            "Do not use shell, filesystem, web, MCP, or any Codex tools. Treat the JSON below "
            "as the complete conversation and available function-tool interface. Choose the "
            "next assistant response only. Return content as a string (empty when calling a "
            "tool) and tool_calls as an array. For every call, arguments must be a JSON object. "
            "Do not execute the function yourself.\n\n"
            + json.dumps({
                "role_label": role,
                "deterministic_seed_label": seed,
                "messages": messages,
                "tools": tools,
            }, ensure_ascii=False, sort_keys=True)
        )

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        seed: int,
    ) -> ModelTurn:
        tool_names = [
            str((tool.get("function") or {}).get("name") or "")
            for tool in tools
            if str((tool.get("function") or {}).get("name") or "")
        ]
        prompt = self._prompt(role, messages, tools, seed)
        async with self._semaphore:
            with tempfile.TemporaryDirectory(prefix="async-rbench-codex-") as temp_name:
                temp_dir = Path(temp_name)
                schema_path = temp_dir / "response.schema.json"
                schema_path.write_text(
                    json.dumps(_codex_cli_output_schema(tools), indent=2),
                    encoding="utf-8",
                )
                command = [
                    self.config.codex_executable,
                    "exec",
                    "-",
                    "--ephemeral",
                    "--json",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--model",
                    model,
                    "--sandbox",
                    "read-only",
                    "--skip-git-repo-check",
                    "--cd",
                    str(temp_dir),
                    "--output-schema",
                    str(schema_path),
                    "-c",
                    f'model_reasoning_effort="{self.config.codex_reasoning_effort}"',
                ]
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=os.environ.copy(),
                )
                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        process.communicate(prompt.encode("utf-8")),
                        timeout=self.config.request_timeout_sec,
                    )
                except asyncio.TimeoutError as exc:
                    process.kill()
                    await process.wait()
                    raise RuntimeError(
                        f"Codex CLI model request timed out after {self.config.request_timeout_sec}s"
                    ) from exc
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise RuntimeError(
                f"Codex CLI exited with code {process.returncode}: "
                f"stderr={stderr[-2000:]} stdout={stdout[-2000:]}"
            )
        payload, total_tokens = _parse_codex_cli_jsonl(stdout)
        tool_specs = {
            str((tool.get("function") or {}).get("name") or ""):
                dict(((tool.get("function") or {}).get("parameters") or {}).get("properties") or {})
            for tool in tools
        }
        calls: list[ToolCall] = []
        assistant_calls: list[dict[str, Any]] = []
        for index, item in enumerate(payload.get("tool_calls") or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            if name not in tool_names:
                raise RuntimeError(f"Codex CLI selected unknown tool {name!r}")
            arguments = item.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise RuntimeError(f"Codex CLI arguments for {name} must be an object")
            decoded_arguments: dict[str, Any] = {}
            for key, value in arguments.items():
                if value is None:
                    continue
                argument_spec = dict(tool_specs.get(name, {}).get(key) or {})
                if (
                    argument_spec.get("type") == "object"
                    and not argument_spec.get("properties")
                    and isinstance(value, str)
                ):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(
                            f"Codex CLI returned malformed JSON object argument {key!r} for {name}"
                        ) from exc
                decoded_arguments[key] = value
            arguments = decoded_arguments
            call_id = str(item.get("id") or f"call-{index}")
            calls.append(ToolCall(id=call_id, name=name, arguments=arguments))
            assistant_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False, sort_keys=True),
                },
            })
        content = str(payload.get("content") or "")
        with self._observation_lock:
            self._observations.add((role.split(":", 1)[0], model, model, None))
        return ModelTurn(
            assistant_message={
                "role": "assistant",
                "content": content or None,
                **({"tool_calls": assistant_calls} if assistant_calls else {}),
            },
            tool_calls=calls,
            total_tokens=total_tokens,
            resolved_model=model,
            system_fingerprint=None,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        with self._observation_lock:
            observations = sorted(self._observations)
        return {
            "transport": "codex_cli_logged_in",
            "model_observations": [
                {
                    "role": role,
                    "requested_model": requested,
                    "resolved_model": resolved,
                    "system_fingerprint": fingerprint,
                }
                for role, requested, resolved, fingerprint in observations
            ],
        }


def function_tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def validate_credential(api_key: str) -> None:
    """Fail fast when a bearer credential would corrupt the Authorization header.

    Authorization headers must be printable ASCII.  A key carrying leading or
    trailing whitespace, a control character, or an invisible non-ASCII byte (a
    stray BOM or non-breaking space from a copy/paste) turns an otherwise valid
    key into a 401 that silently burns the whole episode.  An empty key is
    allowed (some endpoints need no auth); the caller decides whether an
    unauthenticated request is acceptable.
    """
    if not api_key:
        return
    if api_key != api_key.strip():
        raise RuntimeError(
            "model API credential has leading/trailing whitespace; trim the key"
        )
    bad = {hex(ord(ch)) for ch in api_key if ord(ch) < 0x20 or ord(ch) > 0x7E}
    if bad:
        raise RuntimeError(
            "model API credential contains non-Bearer characters "
            f"{sorted(bad)}; expected a flat ASCII token"
        )


def provider_preflight(config: dict[str, Any]) -> str:
    """Return an error reason for a bad provider config, or ``''`` when ready.

    Validates the request surface and the bearer credential so a Unicode/orphan
    key or a malformed endpoint fails before the first episode rather than as a
    burned 401.  The driver preflight and ``build_backend`` both call this so the
    two always agree on what is acceptable.  Empty credentials are allowed unless
    the config says ``api_key_required``.
    """
    api_key_env = str(config.get("api_key_env") or "")
    api_key = os.environ.get(api_key_env) if api_key_env else ""
    if bool(config.get("api_key_required")) and not api_key:
        return f"missing credential {api_key_env!r} (set it before running)"
    try:
        validate_credential(api_key)
    except RuntimeError as exc:
        return f"credential is not a flat bearer token: {exc}"
    if not str(config.get("api_url") or "").strip():
        return "provider config has no api_url"
    if not str(config.get("main_model") or "").strip():
        return "provider config has no main_model"
    return ""


def run_provider_preflight(config_path: str | os.PathLike) -> int:
    """CLI entry for the driver preflight; prints a reason and returns nonzero."""
    try:
        import yaml
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError) as exc:
        print(f"cannot load provider config {config_path}: {exc}")
        return 3
    try:
        reason = provider_preflight(config)
    except Exception as exc:  # noqa: BLE001 — a preflight must fail cleanly, not traceback
        print(f"provider preflight error: {exc}")
        return 3
    if reason:
        print(f"provider preflight failed: {reason}")
        return 3
    print(f"provider preflight OK: model={config.get('main_model')} url={config.get('api_url')}")
    return 0


def build_backend(config: ProviderConfig) -> ModelBackend:
    # The kernel backend factory is provider-neutral. The deterministic
    # ``scripted_test`` backend is a conformance concern and lives in the
    # ``profiles.conformance_mock`` layer; profiles select it themselves.
    if config.backend == "codex_cli":
        return CodexCLIBackend(config)
    if config.backend != "openai_compatible":
        raise ValueError(
            f"kernel backend factory only builds openai_compatible; "
            f"got {config.backend!r} (select a profile backend instead)"
        )
    validate_credential(config.api_key())
    return OpenAICompatibleBackend(config)
