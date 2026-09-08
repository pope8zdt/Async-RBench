"""Claude boundaries use local subprocesses and synthetic credentials only."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.frameworks import claude_code


def _config(**limits):
    return TrackBConfig(
        track="B", framework="claude-code", model="test-model",
        credential_env="TRACK_B_TEST_CLAUDE_KEY", limits=limits,
    )


@pytest.mark.parametrize("backend", ["cli", "sdk"])
def test_claude_child_has_fresh_workspace_and_only_selected_credentials(monkeypatch, backend):
    monkeypatch.setenv("TRACK_B_TEST_CLAUDE_KEY", "selected-synthetic-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unselected-synthetic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-synthetic-key")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "host-config-sentinel")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "unselected-oauth-sentinel")
    monkeypatch.setenv("PYTHONPATH", "host-pythonpath-sentinel")
    monkeypatch.setenv("NODE_OPTIONS", "host-node-options-sentinel")
    create = asyncio.create_subprocess_exec
    calls = []
    fixture = '''import json, os, sys
request = sys.stdin.read()
result = {"cwd": os.getcwd(), "home": os.environ.get("HOME"),
          "config": os.environ.get("CLAUDE_CONFIG_DIR"),
          "api_key": os.environ.get("ANTHROPIC_API_KEY"),
          "forbidden": [key for key in ["OPENAI_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
                        "PYTHONPATH", "NODE_OPTIONS", "TRACK_B_TEST_CLAUDE_KEY"] if key in os.environ]}
print(json.dumps({"result": json.dumps(result), "output_text": json.dumps(result),
                  "usage": {"input_tokens": 3, "output_tokens": 2},
                  "input_tokens": 3, "output_tokens": 2}))
'''

    async def spawn(*args, **kwargs):
        calls.append(args)
        return await create(sys.executable, "-c", fixture, **kwargs)

    monkeypatch.setattr(claude_code.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)
    if backend == "sdk":
        sdk = pytest.importorskip("claude_agent_sdk")

        async def forbidden_parent_query(**_kwargs):
            raise AssertionError("SDK must run in its isolated worker")
            yield

        monkeypatch.setattr(sdk, "query", forbidden_parent_query)
    query = claude_code._cli_query if backend == "cli" else claude_code._sdk_query
    raw = asyncio.run(query(_config(), "public request"))
    captured = json.loads(raw["output_text"])
    assert Path(captured["cwd"]) != Path.cwd()
    assert not Path(captured["cwd"]).exists()
    assert Path(captured["home"]).is_relative_to(Path(captured["cwd"]).parent)
    assert Path(captured["config"]).is_relative_to(Path(captured["cwd"]).parent)
    assert captured["api_key"] == "selected-synthetic-key"
    assert captured["forbidden"] == []
    assert raw["input_tokens"] == 3
    assert all("synthetic-key" not in str(arg) for args in calls for arg in args)
    if backend == "cli":
        args = calls[0]
        assert args[args.index("--tools") + 1] == ""
        assert args[args.index("--setting-sources") + 1] == ""
        assert "--strict-mcp-config" in args
        assert json.loads(args[args.index("--mcp-config") + 1]) == {"mcpServers": {}}
        assert "--disable-slash-commands" in args
        assert "--no-session-persistence" in args
        assert args[args.index("--permission-mode") + 1] == "dontAsk"


def test_sdk_options_disable_native_tools_and_external_configuration(monkeypatch, tmp_path):
    sdk = pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    commands = []

    async def query(*, prompt, options):
        assert prompt == "public request"
        assert options.cwd == str(Path.cwd())
        assert options.tools == []
        assert options.setting_sources == []
        assert options.permission_mode == "dontAsk"
        assert options.mcp_servers == {}
        # Inspect the installed SDK's emitted CLI arguments, not a duplicate builder.
        transport = SubprocessCLITransport(prompt=prompt, options=options)
        transport._cli_path = "claude"
        commands.append(transport._build_command())
        yield sdk.ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="synthetic", result="finished",
            usage={"input_tokens": 7, "output_tokens": 4},
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sdk, "query", query)
    result = asyncio.run(claude_code._sdk_in_process(_config(), "public request"))
    args = commands[0]
    assert args[args.index("--tools") + 1] == ""
    assert "--setting-sources=" in args or (
        "--setting-sources" in args and args[args.index("--setting-sources") + 1] == ""
    )
    assert "--strict-mcp-config" in args
    assert "--disable-slash-commands" in args
    assert "--no-session-persistence" in args
    assert result == {"output_text": "finished", "input_tokens": 7, "output_tokens": 4}


@pytest.mark.parametrize("reason", ["timeout", "cancel"])
def test_claude_cleanup_stops_request_and_descendants(monkeypatch, tmp_path, reason):
    create = asyncio.create_subprocess_exec
    wait_for = asyncio.wait_for
    processes = []
    marker = tmp_path / "child-started"
    request_started = asyncio.Event()
    limit = 1 if reason == "timeout" else 60
    child = (
        "from pathlib import Path; import os, time; "
        f"Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    fixture = (
        "import subprocess, sys, time; sys.stdin.read(); "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(60)"
    )

    async def spawn(*_args, **kwargs):
        process = await create(sys.executable, "-c", fixture, **kwargs)
        processes.append(process)
        return process

    async def request_deadline(awaitable, *, timeout):
        if timeout != limit:
            return await wait_for(awaitable, timeout=timeout)
        # The real subprocess starts under the real guard. For this cleanup
        # test only, start its short deadline after the descendant acknowledges
        # readiness, so slow fixture startup cannot replace the failure path.
        communication = asyncio.ensure_future(awaitable)
        try:
            async with asyncio.timeout(30):
                while not marker.exists() or marker.stat().st_size == 0:
                    if communication.done():
                        raise AssertionError("Fixture exited before descendant readiness")
                    await asyncio.sleep(0.02)
            request_started.set()
            return await wait_for(communication, timeout=timeout)
        finally:
            if not communication.done():
                communication.cancel()
                await asyncio.gather(communication, return_exceptions=True)

    monkeypatch.setattr(claude_code.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(claude_code.asyncio, "wait_for", request_deadline)

    async def exercise():
        task = asyncio.create_task(claude_code._cli_query(_config(request_timeout_sec=limit), "public"))
        ready = asyncio.create_task(request_started.wait())
        try:
            done, _pending = await asyncio.wait((task, ready), timeout=30, return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                await task
            assert ready in done, "Fixture did not reach request execution"
            pid = int(marker.read_text())
            assert _process_alive(pid)
            if reason == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(RuntimeError, match="timed out"):
                    await asyncio.wait_for(task, timeout=15)
            assert processes[0].returncode is not None
            async with asyncio.timeout(5):
                while _process_alive(pid):
                    await asyncio.sleep(0.02)
        finally:
            ready.cancel()
            task.cancel()
            from async_rbench.track_b.frameworks.codex_cli import terminate_process
            for process in processes:
                await terminate_process(process)

    asyncio.run(exercise())


def _process_alive(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        return not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (ProcessLookupError, FileNotFoundError):
        return False


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing-violation cleanup")
@pytest.mark.parametrize("winerror,transient", [(32, True), (32, False), (5, True)])
def test_claude_directory_cleanup_retries_only_bounded_sharing_violations(monkeypatch, winerror, transient):
    create = asyncio.create_subprocess_exec
    temporary_directory = tempfile.TemporaryDirectory
    protect = claude_code.protect_process
    directories = []
    attempts = []
    closed = []

    class RaceDirectory(temporary_directory):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            directories.append(self)

        def cleanup(self):
            assert closed, "Close the process job before releasing its workspace"
            attempts.append(None)
            if len(attempts) < 3 or not transient:
                error = OSError("synthetic directory lock")
                error.winerror = winerror
                raise error
            super().cleanup()

    def guard(process):
        original = protect(process)

        class Guard:
            def close(self):
                original.close()
                closed.append(None)

        return Guard()

    async def spawn(*_args, **kwargs):
        return await create(
            sys.executable, "-c", "import sys; sys.stdin.read(); print('{\"result\":\"finished\"}')",
            **kwargs,
        )

    monkeypatch.setattr(claude_code.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(claude_code.tempfile, "TemporaryDirectory", RaceDirectory)
    monkeypatch.setattr(claude_code, "protect_process", guard)
    try:
        if winerror == 32 and transient:
            result = asyncio.run(claude_code._cli_query(_config(), "public"))
            assert result["output_text"] == "finished"
            assert len(attempts) == 3
            assert not Path(directories[0].name).exists()
        else:
            async def bounded():
                return await asyncio.wait_for(claude_code._cli_query(_config(), "public"), timeout=20)

            with pytest.raises(OSError) as error:
                asyncio.run(bounded())
            assert error.value.winerror == winerror
            if winerror == 5:
                assert len(attempts) == 1
            else:
                assert len(attempts) > 1
    finally:
        for directory in directories:
            temporary_directory.cleanup(directory)


def test_claude_failure_does_not_echo_provider_stderr(monkeypatch):
    create = asyncio.create_subprocess_exec

    async def spawn(*_args, **kwargs):
        return await create(
            sys.executable, "-c",
            "import sys; sys.stdin.read(); sys.stderr.write('synthetic-secret'); sys.exit(9)",
            **kwargs,
        )

    monkeypatch.setattr(claude_code.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(RuntimeError) as error:
        asyncio.run(claude_code._cli_query(_config(), "public"))
    assert "synthetic-secret" not in str(error.value)
    assert "9" in str(error.value)


@pytest.mark.parametrize("backend", ["cli", "sdk"])
def test_installed_claude_advertises_no_native_tools_to_local_endpoint(monkeypatch, backend):
    sdk = pytest.importorskip("claude_agent_sdk")
    executable = Path(sdk.__file__).parent / "_bundled" / ("claude.exe" if os.name == "nt" else "claude")
    if not executable.is_file():
        pytest.skip("Claude SDK wheel has no bundled executable")
    final = '{"output_text":"finished","actions":[]}'
    captures = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path.startswith("/v1/messages/count_tokens"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"input_tokens":7}')
                return
            captures.append(request)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            events = [
                {"type": "message_start", "message": {
                    "id": "msg_synthetic", "type": "message", "role": "assistant",
                    "model": request["model"], "content": [], "stop_reason": None,
                    "stop_sequence": None, "usage": {"input_tokens": 7, "output_tokens": 0},
                }},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": final}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                 "usage": {"output_tokens": 4}},
                {"type": "message_stop"},
            ]
            for event in events:
                self.wfile.write(("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n").encode())
            self.wfile.flush()

    create = asyncio.create_subprocess_exec
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    async def spawn(*args, **kwargs):
        # Test-only provider override; production never inherits these variables.
        environment = kwargs["env"]
        environment["ANTHROPIC_API_KEY"] = "synthetic-local-only-key"
        environment["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
        environment["NO_PROXY"] = "127.0.0.1,localhost"
        for key in list(environment):
            if key.upper() in {"HTTP_PROXY", "HTTPS_PROXY"}:
                del environment[key]
        return await create(*args, **kwargs)

    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: str(executable))
    monkeypatch.setenv("TRACK_B_TEST_CLAUDE_KEY", "synthetic-local-only-key")
    query = claude_code._cli_query if backend == "cli" else claude_code._sdk_query
    try:
        raw = asyncio.run(query(_config(request_timeout_sec=45), "Return a benchmark completion."))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

    assert captures
    assert all(request.get("tools", []) == [] for request in captures)
    context = json.dumps(captures)
    assert "Return a benchmark completion." in context
    for forbidden in ("AGENTS.md", "formal-47", "<skills_instructions>", "synthetic-local-only-key"):
        assert forbidden not in context
    assert raw == {"output_text": final, "input_tokens": 7, "output_tokens": 4}
