from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.contracts import FrameworkRequest


def driver():
    name = "async_rbench.track_b.frameworks.codex_cli"
    assert importlib.util.find_spec(name) is not None, "Codex CLI runtime is not implemented"
    return importlib.import_module(name)


def config(**options):
    return TrackBConfig(
        track="B", framework="codex-cli", model="gpt-5.6-luna",
        framework_options={"reasoning_effort": "medium", **options},
        limits={"request_timeout_sec": 10},
    )


def request():
    return FrameworkRequest(
        messages=({"role": "user", "content": "Inspect /app using terminal."},),
        tools=({"type": "function", "function": {
            "name": "terminal", "parameters": {
                "type": "object", "properties": {"command": {"type": "string"}},
                "required": ["command"], "additionalProperties": False,
            },
        }},),
    )


def output(command="ls -la /app"):
    return json.dumps({"output_text": "Inspecting workspace", "actions": [
        {"kind": "terminal", "arguments": {"command": command}},
    ]})


def events(text=None, usage=None, extra=()):
    return "\n".join(json.dumps(e) for e in [
        {"type": "thread.started", "thread_id": "test-thread"},
        {"type": "turn.started"},
        *extra,
        {"type": "item.completed", "item": {"type": "agent_message", "text": text or output()}},
        {"type": "turn.completed", "usage": usage if usage is not None else {
            "input_tokens": 20, "cached_input_tokens": 15, "output_tokens": 7,
        }},
    ]).encode()


def test_normalizes_cli_output_and_counts_cached_input_only_once():
    result = driver().decode_codex_result(events(), output(), request())
    assert result.output_text == "Inspecting workspace"
    assert result.actions[0].arguments == {"command": "ls -la /app"}
    assert result.usage == {"input_tokens": 20, "output_tokens": 7}
    assert result.resolved_model == ""


def test_typed_command_preserves_backslashes_quotes_and_newlines():
    command = 'python -c "print(\'C:\\\\tasks\\\\results\')"\nprintf \'\\\\d+\\\\.csv\'\n'
    text = output(command)
    result = driver().decode_codex_result(events(text=text), text, request())
    assert result.actions[0].arguments == {"command": command}


def test_strict_tool_branches_match_kind_to_parameters():
    from jsonschema import Draft202012Validator, ValidationError
    from async_rbench.profiles.reference_scaffold_api.runtime import ChildAgent

    child_request = FrameworkRequest(messages=(), tools=tuple(ChildAgent.tools()))
    schema = driver().response_schema(child_request)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    payload = {"output_text": "Inspect", "actions": [{
        "kind": "terminal", "arguments": {"command": "pwd", "timeout_seconds": None},
    }]}
    validator.validate(payload)
    payload["actions"][0]["kind"] = "submit_result"
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_optional_null_is_omitted_before_original_tool_execution():
    from async_rbench.profiles.reference_scaffold_api.runtime import ChildAgent

    child_request = FrameworkRequest(messages=(), tools=tuple(ChildAgent.tools()))
    text = json.dumps({"output_text": "Inspect", "actions": [{
        "kind": "terminal", "arguments": {"command": "pwd", "timeout_seconds": None},
    }]})
    result = driver().decode_codex_result(events(text=text), text, child_request)
    assert result.actions[0].arguments == {"command": "pwd"}


def test_open_evidence_object_round_trips_without_nested_json_text():
    from async_rbench.profiles.reference_scaffold_api.runtime import ChildAgent

    child_request = FrameworkRequest(messages=(), tools=tuple(ChildAgent.tools()))
    evidence = {"entries": [
        {"key": "path", "value": "C:\\task\\report.json"},
        {"key": "metrics", "value": {"entries": [{"key": "rows", "value": 12}]}},
        {"key": "flags", "value": [True, None, "observed"]},
    ]}
    text = json.dumps({"output_text": "Validate", "actions": [{
        "kind": "validate_result", "arguments": {
            "summary": "observed facts", "evidence": evidence, "files": ["report.json"],
        },
    }]})
    result = driver().decode_codex_result(events(text=text), text, child_request)
    assert result.actions[0].arguments["evidence"] == {
        "path": "C:\\task\\report.json", "metrics": {"rows": 12},
        "flags": [True, None, "observed"],
    }


@pytest.mark.parametrize("arguments", [{}, {"command": 123}, {"command": "pwd", "extra": True}])
def test_typed_arguments_are_validated_locally_before_execution(arguments):
    text = json.dumps({"output_text": "Inspect", "actions": [{"kind": "terminal", "arguments": arguments}]})
    with pytest.raises(ValueError, match="schema"):
        driver().decode_codex_result(events(text=text), text, request())


def test_open_object_original_constraints_are_checked_after_decoding():
    custom = FrameworkRequest(messages=(), tools=({"type": "function", "function": {
        "name": "custom", "parameters": {
            "type": "object", "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        },
    }},))
    text = json.dumps({"output_text": "Check", "actions": [{
        "kind": "custom", "arguments": {"entries": [{"key": "count", "value": "wrong type"}]},
    }]})
    with pytest.raises(ValueError, match="schema"):
        driver().decode_codex_result(events(text=text), text, custom)


def test_open_object_duplicate_keys_are_rejected():
    custom = FrameworkRequest(messages=(), tools=({"type": "function", "function": {
        "name": "custom", "parameters": {"type": "object"},
    }},))
    text = json.dumps({"output_text": "Check", "actions": [{
        "kind": "custom", "arguments": {"entries": [
            {"key": "same", "value": 1}, {"key": "same", "value": 2},
        ]},
    }]})
    with pytest.raises(ValueError, match="duplicate"):
        driver().decode_codex_result(events(text=text), text, custom)


@pytest.mark.parametrize("parameters", [
    {"oneOf": [{"type": "object"}]},
    {"$ref": "https://untrusted.invalid/tool-schema"},
    {"type": "object", "properties": {"x": {"type": ["string", "null"]}}, "additionalProperties": False},
    {"type": "object", "properties": {"x": True}, "additionalProperties": False},
])
def test_unsupported_custom_schemas_fail_before_a_model_request(parameters):
    custom = FrameworkRequest(messages=(), tools=({"type": "function", "function": {
        "name": "custom", "parameters": parameters,
    }},))
    with pytest.raises(ValueError, match="unsupported"):
        driver().response_schema(custom)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nonfinite_json_numbers_are_rejected_before_tool_execution(value):
    custom = FrameworkRequest(messages=(), tools=({"type": "function", "function": {
        "name": "custom", "parameters": {"type": "object"},
    }},))
    text = '{"output_text":"Check","actions":[{"kind":"custom","arguments":{"entries":[{"key":"n","value":' + value + '}]}}]}'
    with pytest.raises(ValueError, match="finite|constant"):
        driver().decode_codex_result(events(text=text), text, custom)


def test_duplicate_raw_json_keys_are_rejected():
    text = '{"output_text":"first","output_text":"second","actions":[{"kind":"terminal","arguments":{"command":"pwd"}}]}'
    with pytest.raises(ValueError, match="duplicate"):
        driver().decode_codex_result(events(text=text), text, request())


def test_every_current_main_tool_decodes_with_its_original_parameter_contract():
    from async_rbench.profiles.reference_scaffold_api.runtime import ReferenceScaffold

    tools = ReferenceScaffold.main_tools(SimpleNamespace(start={
        "allowed_artifacts": ["artifact-1"], "allowed_work_units": ["workstream-1"],
    }))
    main_request = FrameworkRequest(messages=(), tools=tuple(tools))
    examples = [
        ("terminal", {"command": "pwd", "timeout_seconds": None}),
        ("spawn_subagent", {"workstream_id": "workstream-1", "task": "Inspect", "targets": [], "expected_output": "report", "priority": None}),
        ("list_subagents", {}),
        ("wait_for_results", {"child_ids": [], "timeout_seconds": 0, "return_when": "any"}),
        ("cancel_subagent", {"child_id": "child-1", "reason": "done"}),
        ("acknowledge_result", {"completion_id": "completion-1", "decision": "use", "reason": "observed"}),
        ("promote_child_path", {"completion_id": "completion-1", "source_path": "report", "destination_path": "report"}),
        ("commit_artifact", {"artifact_id": "artifact-1", "version": "v1", "lineage_completion_ids": [], "evidence_paths": None, "final": None}),
        ("verify_current_state", {"artifact_ids": ["artifact-1"], "lineage_completion_ids": []}),
        ("finish", {"status": "incomplete", "summary": "stopped"}),
    ]
    text = json.dumps({"output_text": "Selected actions", "actions": [
        {"kind": name, "arguments": arguments} for name, arguments in examples
    ]})
    result = driver().decode_codex_result(events(text=text), text, main_request)
    assert [action.kind for action in result.actions] == [name for name, _ in examples]
    assert result.actions[2].arguments == {}
    assert result.actions[3].arguments["timeout_seconds"] == 0
    assert "final" not in result.actions[7].arguments


def test_required_nullable_value_is_preserved():
    custom = FrameworkRequest(messages=(), tools=({"type": "function", "function": {
        "name": "custom", "parameters": {
            "type": "object", "properties": {"value": {"type": ["string", "null"]}},
            "required": ["value"], "additionalProperties": False,
        },
    }},))
    text = json.dumps({"output_text": "Check", "actions": [{"kind": "custom", "arguments": {"value": None}}]})
    result = driver().decode_codex_result(events(text=text), text, custom)
    assert result.actions[0].arguments == {"value": None}


def test_nullable_type_enum_does_not_add_null_when_source_enum_excludes_it():
    from jsonschema import Draft202012Validator

    custom = FrameworkRequest(messages=(), tools=({"type": "function", "function": {
        "name": "custom", "parameters": {
            "type": "object", "properties": {"value": {"type": ["string", "null"], "enum": ["allowed"]}},
            "required": ["value"], "additionalProperties": False,
        },
    }},))
    value = {"output_text": "Check", "actions": [{"kind": "custom", "arguments": {"value": None}}]}
    assert not Draft202012Validator(driver().response_schema(custom)).is_valid(value)


def test_disabled_code_mode_warning_is_compatible_with_completed_tool_free_turn():
    stdout = events(extra=[{"type": "item.completed", "item": {
        "type": "error", "message": "Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed.",
    }}])
    assert driver().decode_codex_result(stdout, output(), request()).actions


def test_unknown_error_item_is_not_silently_ignored():
    stdout = events(extra=[{"type": "item.completed", "item": {"type": "error", "message": "Model failed unexpectedly"}}])
    with pytest.raises(RuntimeError):
        driver().decode_codex_result(stdout, output(), request())


def test_completed_turn_after_transport_reconnect_and_fallback_is_accepted():
    stdout = events(extra=[
        {"type": "error", "message": "Reconnecting... 2/5 (request timed out)"},
        {"type": "item.completed", "item": {"type": "error", "message":
            "Falling back from WebSockets to HTTPS transport. request timed out"}},
    ])
    result = driver().decode_codex_result(stdout, output(), request())
    assert result.actions[0].arguments == {"command": "ls -la /app"}
    assert result.usage == {"input_tokens": 20, "output_tokens": 7}


def test_transport_reconnect_without_completed_turn_is_rejected():
    stdout = json.dumps({"type": "error", "message": "Reconnecting... 2/5 (request timed out)"}).encode()
    with pytest.raises(RuntimeError, match="completed"):
        driver().decode_codex_result(stdout, output(), request())


@pytest.mark.parametrize("kind", ["command_execution", "file_change", "mcp_tool_call", "web_search", "collab_tool_call"])
def test_rejects_any_native_action_even_if_final_json_is_valid(kind):
    stdout = events(extra=[{"type": "item.started", "item": {"type": kind}}])
    with pytest.raises(RuntimeError, match="native"):
        driver().decode_codex_result(stdout, output(), request())


@pytest.mark.parametrize("extra", [
    {"type": "error", "message": "failed"},
    {"type": "turn.failed", "error": {"message": "failed"}},
])
def test_failed_events_are_not_scored_as_success(extra):
    with pytest.raises(RuntimeError):
        driver().decode_codex_result(events(extra=[extra]), output(), request())


def test_requires_completed_turn_and_usage():
    with pytest.raises(RuntimeError, match="completed"):
        driver().decode_codex_result(b'{"type":"turn.started"}', output(), request())
    with pytest.raises(RuntimeError, match="usage"):
        driver().decode_codex_result(events(usage={}), output(), request())


def test_final_file_must_match_last_completed_message():
    first = output("echo first")
    last = output("echo last")
    stdout = events(text=last, extra=[{"type": "item.completed", "item": {"type": "agent_message", "text": first}}])
    with pytest.raises(RuntimeError, match="unbound"):
        driver().decode_codex_result(stdout, first, request())


@pytest.mark.parametrize("text", ["", "\n", "not JSON", '{"output_text":"","actions":[]}',
    '{"output_text":"working","actions":[{"kind":"terminal","arguments":[1]}]}',
    '{"output_text":"working","actions":[{"kind":"unavailable","arguments":{}}]}',
])
def test_invalid_final_outputs_fail_explicitly(text):
    with pytest.raises((ValueError, RuntimeError)):
        driver().decode_codex_result(events(text=text), text, request())


def test_child_environment_excludes_api_keys_routing_and_parent_context(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("CODEX_API_KEY", "test-secret")
    monkeypatch.setenv("TRACK_B_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unselected.invalid")
    monkeypatch.setenv("CODEX_THREAD_ID", "parent-thread")
    monkeypatch.setenv("CODEX_HOME", "C:/test/account-home")
    child = driver().child_environment()
    assert child.get("CODEX_HOME") == "C:/test/account-home"
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "TRACK_B_API_KEY", "OPENAI_BASE_URL", "CODEX_THREAD_ID"):
        assert key not in child


def test_command_uses_selected_model_and_no_native_tools(tmp_path):
    args = driver().build_command(config(), tmp_path, executable="codex-test")
    assert args[0] == "codex-test"
    assert args[args.index("--model") + 1] == "gpt-5.6-luna"
    assert args[args.index("--sandbox") + 1] == "read-only"
    for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check", "--json", "--output-schema"):
        assert flag in args
    assert 'model_reasoning_effort="medium"' in args
    assert 'model_provider="openai_https"' in args
    assert 'model_providers.openai_https={name="OpenAI",wire_api="responses",requires_openai_auth=true,supports_websockets=false}' in args
    assert 'web_search="disabled"' in args
    assert 'project_doc_max_bytes=0' in args
    assert 'developer_instructions=""' in args
    assert 'tools.experimental_request_user_input.enabled=false' in args
    assert any(arg.startswith("model_instructions_file=") for arg in args)
    assert any(arg.startswith("model_catalog_json=") for arg in args)
    assert any(arg.startswith("skills.config=") for arg in args)
    disabled = {args[i + 1] for i, value in enumerate(args[:-1]) if value == "--disable"}
    assert {"shell_tool", "unified_exec", "code_mode_host", "apps", "plugins", "multi_agent", "computer_use", "browser_use", "hooks", "memories"} <= disabled
    assert args[-1] == "-"


def test_disables_exact_skill_files_without_loading_their_contents(tmp_path, monkeypatch):
    mod = driver()
    monkeypatch.setattr(mod.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "account"))
    skill_a = tmp_path / "account/skills/.system/example/SKILL.md"
    skill_b = tmp_path / ".agents/skills/user-skill/SKILL.md"
    for p in (skill_a, skill_b):
        p.parent.mkdir(parents=True)
        p.write_text("DO NOT LOAD THIS TEST SKILL", encoding="utf-8")
    values = mod.disabled_skill_config()
    assert skill_a.as_posix() in values and skill_b.as_posix() in values
    assert values.count("enabled=false") >= 2
    assert "DO NOT LOAD" not in values


def test_local_catalog_preserves_model_identity_and_disables_forced_native_tools():
    source = {"models": [{"slug": "gpt-5.6-luna", "context_window": 272000,
        "tool_mode": "code_mode_only", "apply_patch_tool_type": "freeform"}]}
    result = driver().make_model_catalog(source, "gpt-5.6-luna")
    selected = result["models"][0]
    assert selected["slug"] == "gpt-5.6-luna"
    assert selected["context_window"] == 272000
    assert selected["tool_mode"] is None
    assert selected["apply_patch_tool_type"] is None
    assert selected["multi_agent_version"] is None
    assert selected["supports_search_tool"] is False
    assert selected["node_repl_disabled"] is True
    assert source["models"][0]["tool_mode"] == "code_mode_only"
    with pytest.raises(ValueError, match="catalog"):
        driver().make_model_catalog(source, "missing-model")


def test_subprocess_uses_fresh_directory_schema_and_stdin(monkeypatch):
    mod = driver()
    monkeypatch.setattr(mod, "check_cli_login", lambda: (True, "ChatGPT login ready"))
    monkeypatch.setattr(mod.shutil, "which", lambda _: "codex-test")
    monkeypatch.setattr(mod, "load_model_catalog", lambda *a: {"models": [{"slug": "gpt-5.6-luna"}]})
    captured = []
    protected = set()

    def protect(process):
        protected.add(process)
        return SimpleNamespace(close=lambda: protected.remove(process))

    monkeypatch.setattr(mod, "protect_process", protect)

    async def spawn(*args, **kwargs):
        cwd = Path(kwargs["cwd"])
        assert not (cwd / ".git").exists()
        assert not (cwd / "AGENTS.md").exists()
        schema = json.loads(Path(args[args.index("--output-schema") + 1]).read_text())
        assert schema["additionalProperties"] is False
        branch = schema["properties"]["actions"]["items"]["anyOf"][0]
        assert branch["properties"]["kind"]["enum"] == ["terminal"]
        captured.append((args, kwargs))
        class Process:
            returncode = 0
            async def communicate(self, input):
                assert self in protected, "protect the process before sending model input"
                assert b"PUBLIC REQUEST JSON" in input
                assert b"Inspect /app" in input
                Path(args[args.index("--output-last-message") + 1]).write_text(output(), encoding="utf-8")
                return events(), b""
        return Process()

    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", spawn)
    runtime = mod.CodexCLIRuntime(config())
    first = asyncio.run(runtime.run(request()))
    second = asyncio.run(runtime.run(request()))
    assert first.actions == second.actions
    assert captured[0][1]["cwd"] != captured[1][1]["cwd"]
    assert all(not Path(kwargs["cwd"]).exists() for _, kwargs in captured)
    assert not protected


def test_timeout_terminates_own_process(monkeypatch):
    mod = driver()
    monkeypatch.setattr(mod, "check_cli_login", lambda: (True, "ready"))
    monkeypatch.setattr(mod.shutil, "which", lambda _: "codex-test")
    monkeypatch.setattr(mod, "load_model_catalog", lambda *a: {"models": [{"slug": "gpt-5.6-luna"}]})
    monkeypatch.setattr(mod, "protect_process", lambda process: None)
    stopped = []
    class Process:
        returncode = None
        async def communicate(self, input):
            raise asyncio.TimeoutError
    process = Process()
    async def spawn(*args, **kwargs):
        return process
    async def terminate(target):
        assert target is process
        target.returncode = -1
        stopped.append(target)
    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(mod, "terminate_process", terminate)
    with pytest.raises(RuntimeError, match="timed out"):
        asyncio.run(mod.CodexCLIRuntime(config()).run(request()))
    assert stopped == [process]


def test_windows_cleanup_falls_back_when_taskkill_returns_failure(monkeypatch):
    mod = driver()
    if mod.os.name != "nt":
        pytest.skip("Windows process cleanup")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1))
    class Process:
        pid = 987654321  # No real command is issued in this test.
        returncode = None
        killed = False
        def kill(self):
            self.killed = True
            self.returncode = -9
        async def wait(self):
            assert self.killed, "failed taskkill must fall back to process.kill"
            return self.returncode
    process = Process()
    asyncio.run(mod.terminate_process(process))
    assert process.killed


@pytest.mark.parametrize("failure", ["cancelled", "protection_unavailable"])
def test_interrupted_request_cleans_up_without_unprotected_model_input(monkeypatch, failure):
    mod = driver()
    monkeypatch.setattr(mod, "check_cli_login", lambda: (True, "ready"))
    monkeypatch.setattr(mod.shutil, "which", lambda _: "codex-test")
    monkeypatch.setattr(mod, "load_model_catalog", lambda *a: {"models": [{"slug": "gpt-5.6-luna"}]})
    state = {"prompt_sent": False, "guard_closed": False}

    async def exercise():
        entered = asyncio.Event()

        class Process:
            returncode = None

            async def communicate(self, data):
                state["prompt_sent"] = True
                entered.set()
                await asyncio.Future()

        process = Process()

        async def spawn(*args, **kwargs):
            return process

        def protect(target):
            assert target is process
            if failure == "protection_unavailable":
                raise RuntimeError("process ownership unavailable")
            return SimpleNamespace(close=lambda: state.update(guard_closed=True))

        async def terminate(target):
            assert target is process
            target.returncode = -1

        monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(mod, "protect_process", protect)
        monkeypatch.setattr(mod, "terminate_process", terminate)
        task = asyncio.create_task(mod.CodexCLIRuntime(config()).run(request()))
        if failure == "cancelled":
            await asyncio.wait_for(entered.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert state["guard_closed"]
        else:
            with pytest.raises(RuntimeError, match="process ownership unavailable"):
                await task
            assert not state["prompt_sent"]
        assert process.returncode == -1

    asyncio.run(exercise())


@pytest.mark.skipif(os.name != "nt", reason="Windows process ownership")
@pytest.mark.parametrize("kill_launcher", [False, True], ids=["adapter", "launcher"])
def test_cli_descendants_exit_when_adapter_or_its_launcher_is_killed(tmp_path, kill_launcher):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    ready_path = tmp_path / "tree.json"
    descendants_path = tmp_path / "descendants.json"
    python = sys._base_executable
    child_code = (
        "import json, os, subprocess, sys, time; from pathlib import Path; "
        "assert sys.stdin.readline() == 'begin\\n'; "
        f"child = subprocess.Popen([{python!r}, '-c', 'import time; time.sleep(60)'], "
        "creationflags=subprocess.CREATE_NO_WINDOW); "
        f"Path({str(descendants_path)!r}).write_text(json.dumps([os.getpid(), child.pid])); "
        "time.sleep(60)"
    )
    adapter_code = (
        "import json, os, subprocess, sys; from pathlib import Path; "
        f"sys.path = {sys.path!r}; "
        "from async_rbench.track_b.frameworks import codex_cli as mod; "
        f"child = subprocess.Popen([{python!r}, '-c', {child_code!r}], stdin=subprocess.PIPE, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW); "
        "guard = mod.protect_process(child); "
        "child.stdin.write(b'begin\\n'); child.stdin.flush(); "
        f"Path({str(ready_path)!r}).write_text(json.dumps([os.getpid(), child.pid])); "
        "child.wait(); guard.close() if guard else None"
    )
    if kill_launcher:
        target_code = (
            "import subprocess; "
            f"process = subprocess.Popen([{python!r}, '-c', {adapter_code!r}], "
            "creationflags=subprocess.CREATE_NO_WINDOW); process.wait()"
        )
    else:
        target_code = adapter_code
    target = subprocess.Popen(
        [python, "-c", target_code], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    handles = []
    try:
        deadline = time.monotonic() + 30
        while not ready_path.exists() or not descendants_path.exists():
            assert target.poll() is None, target.stderr.read().decode(errors="replace")
            assert time.monotonic() < deadline, "test process tree did not start"
            time.sleep(0.02)
        pids = set(json.loads(ready_path.read_text()) + json.loads(descendants_path.read_text()))
        for pid in pids:
            handle = kernel.OpenProcess(0x00100001, False, pid)  # SYNCHRONIZE | TERMINATE
            assert handle, ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
        target.kill()  # Only the adapter/launcher created by this test.
        target.wait(timeout=5)
        assert all(kernel.WaitForSingleObject(handle, 5000) == 0 for handle in handles), (
            "the adapter's CLI process tree survived its owner"
        )
    finally:
        try:
            if target.poll() is None:
                cleanup = subprocess.run(
                    ["taskkill", "/PID", str(target.pid), "/T", "/F"],
                    capture_output=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                assert cleanup.returncode == 0 or target.poll() is not None, (
                    "failed to stop the process tree created by this test"
                )
        finally:
            for handle in handles:
                if kernel.WaitForSingleObject(handle, 0) == 258:
                    kernel.TerminateProcess(handle, 1)
                kernel.CloseHandle(handle)
            if target.poll() is None:
                target.kill()
            target.wait(timeout=5)
            target.stderr.close()


def test_login_probe_accepts_only_saved_chatgpt_auth(monkeypatch):
    mod = driver()
    monkeypatch.setattr(mod.shutil, "which", lambda _: "codex-test")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr="Logged in using ChatGPT"))
    assert mod.check_cli_login()[0]
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr="Logged in using an API key: sk-test-hidden"))
    ready, detail = mod.check_cli_login()
    assert not ready
    assert "sk-test-hidden" not in detail


@pytest.mark.parametrize("options", [{"base_url": "https://other.invalid"}, {"reasoning_effort": "ultra"}, {"shell": True}])
def test_unsupported_options_are_rejected_before_process_launch(options):
    with pytest.raises(ValueError):
        driver().build_command(config(**options), Path("unused"), executable="codex-test")
