from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult
from .common import parse_protocol_result, render_protocol_prompt


# These settings were checked against the actual Responses request emitted by
# Codex CLI 0.153.4 using a local mock endpoint, without account credentials.
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "code_mode_host", "code_mode", "apps", "plugins",
    "multi_agent", "multi_agent_v2", "browser_use", "browser_use_external",
    "computer_use", "image_generation", "view_image", "hooks", "goals",
    "sleep_tool", "skill_search", "skill_mcp_dependency_install", "tool_suggest",
    "workspace_dependencies", "memories", "shell_snapshot", "in_app_browser",
    "remote_plugin", "recommended_plugins", "unbounded_connection_retries",
)
_ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "USERPROFILE",
    "HOMEDRIVE", "HOMEPATH", "HOME", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
    "TMPDIR", "CODEX_HOME", "LANG", "LC_ALL", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
}
_MAX_EVENT_BYTES = 8 * 1024 * 1024
MODEL_INSTRUCTIONS = (
    "You are the decision-making agent inside Async-RBench Track B. "
    "Use only the supplied public task, message history and benchmark tool schemas. "
    "Select the next benchmark actions and return the required structured response. "
    "The benchmark executes those actions in isolated workspaces and supplies observations "
    "on your next turn. Do not assume that a proposed action has already executed."
)


def child_environment() -> dict[str, str]:
    """Keep official saved auth accessible without inheriting provider overrides."""
    return {key: value for key, value in os.environ.items() if key.upper() in _ENV_ALLOWLIST}


def check_cli_login() -> tuple[bool, str]:
    executable = shutil.which("codex")
    if executable is None:
        return False, "Codex CLI is not installed"
    try:
        result = subprocess.run(
            [executable, "login", "status"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15, env=child_environment(),
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "Codex CLI login status could not be checked"
    if result.returncode == 0 and "Logged in using ChatGPT" in (result.stdout + result.stderr):
        return True, "Codex CLI saved ChatGPT login is ready"
    # Never echo auth command output: API-key login status may include key material.
    return False, "Codex CLI requires saved ChatGPT authentication; run codex login"


def disabled_skill_config() -> str:
    # This CLI matches exact SKILL.md paths, not parent folders. Enumerate only
    # skill installation roots and never load their content into the agent.
    account_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    roots = [account_home / "skills", Path.home() / ".agents" / "skills"]
    if os.name != "nt":
        roots.append(Path("/etc/codex/skills"))
    paths = sorted({path.as_posix() for root in roots if root.is_dir() for path in root.rglob("SKILL.md")})
    return "skills.config=[" + ",".join(
        "{path=" + json.dumps(path) + ",enabled=false}" for path in paths
    ) + "]"


def make_model_catalog(source: dict[str, Any], model: str) -> dict[str, Any]:
    entries = [item for item in source.get("models", []) if item.get("slug") == model]
    if len(entries) != 1:
        raise ValueError("requested Codex model must appear exactly once in the CLI catalog")
    selected = copy.deepcopy(entries[0])
    # CLI model metadata can force Code Mode despite disabled feature flags.
    # Change tool presentation only; keep the requested model and its other
    # capabilities intact. This catalog exists only for this subprocess.
    selected["tool_mode"] = None
    selected["apply_patch_tool_type"] = None
    selected["multi_agent_version"] = None
    selected["supports_search_tool"] = False
    selected["node_repl_disabled"] = True
    return {"models": [selected]}


def load_model_catalog(executable: str, model: str) -> dict[str, Any]:
    result = subprocess.run(
        [executable, "debug", "models", "--bundled"], capture_output=True, text=True,
        encoding="utf-8", errors="strict", timeout=15, env=child_environment(),
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    if result.returncode != 0:
        raise RuntimeError("Codex CLI bundled model catalog could not be loaded")
    return make_model_catalog(json.loads(result.stdout), model)


def build_command(config: TrackBConfig, directory: Path, *, executable: str) -> list[str]:
    unknown = set(config.framework_options) - {"reasoning_effort"}
    if unknown:
        raise ValueError("unsupported Codex CLI framework options: " + ", ".join(sorted(unknown)))
    if config.credential_env:
        raise ValueError("Codex CLI uses saved ChatGPT login, not credential_env")
    effort = config.framework_options.get("reasoning_effort", "medium")
    if effort not in {"low", "medium", "high", "xhigh", "max"}:
        raise ValueError("unsupported Codex CLI reasoning_effort")
    if "max_output_tokens" in config.limits:
        raise ValueError("Codex CLI does not expose max_output_tokens; use its request timeout")
    args = [
        executable, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
        "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
        "--model", config.model, "--cd", str(directory),
        "--output-schema", str(directory / "response-schema.json"),
        "--output-last-message", str(directory / "final.json"),
        "-c", f"model_reasoning_effort={json.dumps(effort)}",
        # Built-in provider entries cannot be overridden. Keep official saved
        # auth/default endpoint selection and disable only WebSocket transport.
        "-c", 'model_provider="openai_https"',
        "-c", 'model_providers.openai_https={name="OpenAI",wire_api="responses",requires_openai_auth=true,supports_websockets=false}',
        "-c", 'web_search="disabled"', "-c", "project_doc_max_bytes=0",
        "-c", "features.skip_host_skill_discovery=true",
        "-c", 'developer_instructions=""',
        "-c", "model_instructions_file=" + json.dumps((directory / "instructions.txt").as_posix()),
        "-c", "model_catalog_json=" + json.dumps((directory / "model-catalog.json").as_posix()),
        "-c", disabled_skill_config(),
        "-c", "suppress_unstable_features_warning=true",
        "-c", "tools.experimental_request_user_input.enabled=false",
    ]
    for feature in DISABLED_FEATURES:
        args.extend(["--disable", feature])
    return [*args, "-"]


def _strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False,
    }


def _json_value_definitions() -> dict[str, Any]:
    # Arbitrary evidence keys cannot be expressed as strict object properties.
    # Entries preserve keys and all JSON value types without JSON inside strings.
    return {
        "json_object": _strict_object({"entries": {
            "type": "array", "items": _strict_object({
                "key": {"type": "string"}, "value": {"$ref": "#/$defs/json_value"},
            }),
        }}),
        "json_value": {"anyOf": [
            {"type": "string"}, {"type": "number"}, {"type": "boolean"},
            {"type": "null"},
            {"type": "array", "items": {"$ref": "#/$defs/json_value"}},
            {"$ref": "#/$defs/json_object"},
        ]},
    }


def _strict_parameter_schema(source: dict[str, Any]) -> dict[str, Any]:
    from jsonschema import Draft202012Validator

    if not isinstance(source, dict):
        raise ValueError("unsupported Codex tool schema: typed object schema required")
    if any(isinstance(value, (dict, list)) for value in source.get("enum", [])):
        raise ValueError("unsupported Codex tool schema object/array enum")
    kind = source.get("type")
    if isinstance(kind, list):
        if len(kind) != 2 or "null" not in kind:
            raise ValueError("unsupported Codex tool schema type union")
        nonnull = next(value for value in kind if value != "null")
        nonnull_source = {**source, "type": nonnull}
        enum = source.get("enum")
        enum_values = [value for value in enum if value is not None] if enum is not None else None
        if enum_values:
            nonnull_source["enum"] = enum_values
        elif enum is not None:
            nonnull_source.pop("enum")
        converted = _strict_parameter_schema(nonnull_source)
        branches = [converted] if enum is None or enum_values else []
        if Draft202012Validator(source).is_valid(None):
            branches.append({"type": "null"})
        if not branches:
            raise ValueError("unsupported Codex tool schema empty nullable enum")
        return {"anyOf": branches}
    keywords = {
        "object": {"properties", "required", "additionalProperties"},
        "array": {"items", "minItems", "maxItems"},
        "string": {"minLength", "maxLength", "pattern", "format"},
        "integer": {"minimum", "maximum"},
        "number": {"minimum", "maximum"}, "boolean": set(), "null": set(),
    }
    if kind not in keywords:
        raise ValueError("unsupported Codex tool schema type")
    unknown = set(source) - keywords[kind] - {"type", "description", "title", "enum"}
    if unknown:
        raise ValueError("unsupported Codex tool schema keywords: " + ", ".join(sorted(unknown)))
    if kind == "array":
        if not isinstance(source.get("items"), dict):
            raise ValueError("unsupported Codex tool schema array without typed items")
        return {**source, "items": _strict_parameter_schema(source["items"])}
    if kind != "object":
        return copy.deepcopy(source)
    properties = source.get("properties", {})
    required = source.get("required", [])
    converted = {}
    for name, schema in properties.items():
        converted[name] = _strict_parameter_schema(schema)
        if name not in required:
            if Draft202012Validator(schema).is_valid(None):
                raise ValueError("unsupported Codex tool schema optional nullable property")
            converted[name] = {"anyOf": [converted[name], {"type": "null"}]}
    additional = source.get("additionalProperties", True)
    if type(additional) is not bool:
        raise ValueError("unsupported Codex tool schema typed additionalProperties")
    if additional:
        return {
            "$ref": "#/$defs/json_object",
            "description": (
                str(source.get("description") or "")
                + " Represent this arbitrary object as entries of key and value. "
                "Nested objects also use entries; arrays and scalar values remain typed JSON."
            ).strip(),
        }
    return _strict_object(converted)


def _tool_parameter_schemas(request: FrameworkRequest) -> dict[str, dict[str, Any]]:
    from jsonschema import Draft202012Validator, SchemaError

    schemas = {}
    for tool in request.tools:
        function = tool.get("function") or {}
        name, parameters = function.get("name"), function.get("parameters")
        if not isinstance(name, str) or not name or name in schemas:
            raise ValueError("unsupported Codex tool schema missing or duplicate function name")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise ValueError("unsupported Codex tool schema: parameters must be an object schema")
        try:
            Draft202012Validator.check_schema(parameters)
        except SchemaError as exc:
            raise ValueError("unsupported Codex tool parameter schema") from exc
        _strict_parameter_schema(parameters)  # Reject unsupported constructs before any model call.
        schemas[name] = parameters
    return schemas


def response_schema(request: FrameworkRequest) -> dict[str, Any]:
    schemas = _tool_parameter_schemas(request)
    branches = [
        _strict_object({
            "kind": {"type": "string", "enum": [name]},
            "arguments": _strict_parameter_schema(parameters),
        })
        for name, parameters in sorted(schemas.items())
    ]
    actions: dict[str, Any] = {"type": "array", "items": {"anyOf": branches}}
    if not branches:
        actions = {"type": "array", "items": _strict_object({}), "maxItems": 0}
    return {
        **_strict_object({"output_text": {"type": "string"}, "actions": actions}),
        "$defs": _json_value_definitions(),
    }


def _decode_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_json_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for entry in value["entries"]:
        if entry["key"] in result:
            raise ValueError("Codex CLI returned duplicate object entry keys")
        result[entry["key"]] = _decode_json_value(entry["value"])
    return result


def _decode_arguments(value: Any, source: dict[str, Any]) -> Any:
    if value is None:
        return None
    kind = source["type"]
    if isinstance(kind, list):
        kind = next(item for item in kind if item != "null")
    if kind == "array":
        return [_decode_arguments(item, source["items"]) for item in value]
    if kind != "object":
        return value
    if source.get("additionalProperties", True):
        return _decode_json_value(value)
    return {
        name: _decode_arguments(item, source["properties"][name])
        for name, item in value.items()
        if item is not None or name in source.get("required", [])
    }


def _validate_schema(value: Any, schema: dict[str, Any]) -> None:
    from jsonschema import Draft202012Validator, FormatChecker, ValidationError

    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    except ValidationError as exc:
        path = "/".join(str(part) for part in exc.absolute_path) or "response"
        raise ValueError(f"Codex CLI response violates tool schema at {path}") from exc


def _strict_json(text: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Codex CLI returned duplicate JSON object keys")
            value[key] = item
        return value

    def finite_float(number: str) -> float:
        value = float(number)
        if not math.isfinite(value):
            raise ValueError("Codex CLI JSON numbers must be finite")
        return value

    def reject_constant(_value: str) -> None:
        raise ValueError("Codex CLI returned an invalid JSON constant")

    return json.loads(
        text, object_pairs_hook=unique_object,
        parse_float=finite_float, parse_constant=reject_constant,
    )


def decode_codex_result(stdout: bytes, final_text: str, request: FrameworkRequest) -> FrameworkResult:
    if len(stdout) > _MAX_EVENT_BYTES:
        raise RuntimeError("Codex CLI event output exceeded its diagnostic limit")
    completions = []
    messages = []
    for line in stdout.decode("utf-8").splitlines():
        if not line.strip():
            continue
        event = _strict_json(line)
        kind = event.get("type")
        if kind == "error" and str(event.get("message", "")).startswith("Reconnecting... "):
            # Transport retries are diagnostic events. A completed turn with
            # bound final output and valid usage is still required below.
            continue
        if kind in {"error", "turn.failed"}:
            raise RuntimeError("Codex CLI reported a failed model turn")
        if str(kind).startswith("item."):
            item = event.get("item") or {}
            if item.get("type") == "error" and str(item.get("message", "")).startswith((
                "Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed",
                "Falling back from WebSockets to HTTPS transport.",
            )):
                continue
            if item.get("type") not in {"agent_message", "reasoning"}:
                raise RuntimeError("Codex CLI emitted a native action outside the benchmark gateway")
            if kind == "item.completed" and item.get("type") == "agent_message":
                messages.append(str(item.get("text") or ""))
        if kind == "turn.completed":
            completions.append(event)
    if len(completions) != 1:
        raise RuntimeError("Codex CLI must return exactly one completed turn")
    usage = completions[0].get("usage") or {}
    if any(type(usage.get(key)) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens")):
        raise RuntimeError("Codex CLI completed turn has missing or invalid token usage")
    if not final_text.strip() or not messages or messages[-1].strip() != final_text.strip():
        raise RuntimeError("Codex CLI returned empty or unbound final output")
    payload = _strict_json(final_text)
    _validate_schema(payload, response_schema(request))
    schemas = _tool_parameter_schemas(request)
    actions = []
    for action in payload["actions"]:
        source = schemas[action["kind"]]
        arguments = _decode_arguments(action["arguments"], source)
        _validate_schema(arguments, source)
        actions.append({"kind": action["kind"], "arguments": arguments})
    return parse_protocol_result(
        json.dumps({"output_text": payload["output_text"], "actions": actions}), request,
        usage={"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"]},
    )


class _WindowsProcessGuard:
    """Own only one newly spawned CLI tree, never the adapter or its parents."""

    def __init__(self, pid: int) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimit(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimit(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimit),
                ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        }
        for name, (argtypes, restype) in signatures.items():
            function = getattr(kernel, name)
            function.argtypes, function.restype = argtypes, restype
        self._kernel = kernel
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._job = kernel.CreateJobObjectW(None, None)  # Unnamed, non-inheritable handle.
        if not self._job:
            raise ctypes.WinError(ctypes.get_last_error())
        parent = child = None
        try:
            limits = ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(self._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            parent = kernel.OpenProcess(0x00100000, False, os.getppid())  # SYNCHRONIZE only.
            child = kernel.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE.
            if not parent or not child:
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.AssignProcessToJobObject(self._job, child):
                raise ctypes.WinError(ctypes.get_last_error())
            self._watcher = threading.Thread(
                target=self._watch_parent, args=(parent,), daemon=True,
                name="track-b-codex-owner",
            )
            self._watcher.start()
        except BaseException:
            if parent:
                kernel.CloseHandle(parent)
            self._close_job()
            raise
        finally:
            if child:
                kernel.CloseHandle(child)

    def _close_job(self) -> None:
        with self._lock:
            if self._job:
                self._kernel.CloseHandle(self._job)
                self._job = None

    def _watch_parent(self, parent: Any) -> None:
        try:
            while not self._stop.is_set():
                status = self._kernel.WaitForSingleObject(parent, 200)
                if status != 258:  # Parent exited, or monitoring failed: stop this CLI.
                    self._close_job()
                    return
        finally:
            self._kernel.CloseHandle(parent)

    def close(self) -> None:
        self._stop.set()
        self._close_job()
        # The daemon owns the parent handle and releases it after its bounded
        # wait; do not add that polling latency to every benchmark model turn.


def protect_process(process: asyncio.subprocess.Process) -> _WindowsProcessGuard | None:
    # Protect after spawn but before sending a prompt. If the adapter is killed,
    # Windows closes its job handle; if its Python launcher is killed instead,
    # the parent watcher closes it. Neither path can terminate an unrelated tree.
    return _WindowsProcessGuard(process.pid) if os.name == "nt" else None


async def terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if os.name == "nt":
        # PID comes only from the subprocess created by this runtime.
        try:
            result = await asyncio.to_thread(
                subprocess.run, ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0 and process.returncode is None:
                process.kill()
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await asyncio.wait_for(process.wait(), timeout=5)


class CodexCLIRuntime:
    def __init__(self, config: TrackBConfig) -> None:
        self.config = config
        self._login_checked = False
        self._catalog: dict[str, Any] | None = None

    async def run(self, request: FrameworkRequest) -> FrameworkResult:
        executable = shutil.which("codex")
        if executable is None:
            raise RuntimeError("Codex CLI is not installed")
        if not self._login_checked:
            ready, detail = await asyncio.to_thread(check_cli_login)
            if not ready:
                raise RuntimeError(detail)
            self._login_checked = True
        if self._catalog is None:
            self._catalog = await asyncio.to_thread(load_model_catalog, executable, self.config.model)
        # Outside the repository: no parent AGENTS.md, git state or case files.
        with tempfile.TemporaryDirectory(prefix="async-rbench-codex-") as temp:
            directory = Path(temp)
            (directory / "instructions.txt").write_text(MODEL_INSTRUCTIONS, encoding="utf-8")
            (directory / "model-catalog.json").write_text(json.dumps(self._catalog), encoding="utf-8")
            (directory / "response-schema.json").write_text(
                json.dumps(response_schema(request)), encoding="utf-8",
            )
            args = build_command(self.config, directory, executable=executable)
            prompt = (
                render_protocol_prompt(request)
                + "\n\nRESPONSE ENVELOPE: Return each action with kind and a typed arguments object; "
                "do not serialize arguments as JSON text. Use null for omitted optional arguments. "
                "For arbitrary evidence objects, use {\"entries\":[{\"key\":\"fact\",\"value\":123}]}; "
                "nested arbitrary objects also use entries, while arrays and scalar values stay typed. "
                "Select actions only; the benchmark executes them and returns observations on the next turn."
            )
            process = await asyncio.create_subprocess_exec(
                *args, cwd=str(directory), env=child_environment(),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
                   if os.name == "nt" else {"start_new_session": True}),
            )
            guard = None
            try:
                guard = protect_process(process)
                try:
                    stdout, _stderr = await asyncio.wait_for(
                        process.communicate(prompt.encode("utf-8")),
                        timeout=float(self.config.limits.get("request_timeout_sec", 180)),
                    )
                except asyncio.TimeoutError as exc:
                    raise RuntimeError("Codex CLI model request timed out") from exc
                if process.returncode != 0:
                    raise RuntimeError(f"Codex CLI exited with code {process.returncode}")
                final_path = directory / "final.json"
                if not final_path.is_file():
                    raise RuntimeError("Codex CLI did not write its structured final response")
                return decode_codex_result(stdout, final_path.read_text(encoding="utf-8"), request)
            finally:
                try:
                    if process.returncode is None:
                        await terminate_process(process)
                finally:
                    if guard is not None:
                        guard.close()


def build_runtime(config: TrackBConfig) -> CodexCLIRuntime:
    return CodexCLIRuntime(config)
