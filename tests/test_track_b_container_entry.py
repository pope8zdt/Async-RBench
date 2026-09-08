from __future__ import annotations

import ctypes
import io
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _test_env() -> dict[str, str]:
    return {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR") if key in os.environ}


@contextmanager
def _input_after_child_ready(ready: Path, data: bytes = b""):
    read_fd, write_fd = os.pipe()
    stop = threading.Event()
    observed = []

    def writer():
        try:
            while not stop.is_set():
                if ready.exists():
                    observed.append(time.monotonic())
                    os.write(write_fd, data)
                    return
                stop.wait(0.02)
        finally:
            os.close(write_fd)

    worker = threading.Thread(target=writer, daemon=True)
    worker.start()
    with os.fdopen(read_fd, "rb", buffering=0) as stream:
        try:
            yield stream, observed
        finally:
            stop.set()
            worker.join(timeout=2)


def _bootstrap(**changes):
    payload = {
        "operation": "adapter",
        "config": {
            "track": "B", "framework": "deterministic", "model": "fixture",
            "credential_env": "", "components": {}, "limits": {}, "framework_options": {},
            "runtime": {"type": "docker", "image": "track-b:test", "timeout_sec": 20},
        },
        "args": ["--conformance", "--workspace-mode", "disabled"],
        "environment": {},
        "runtime_metadata": {"image_id": "sha256:" + "a" * 64, "os": "linux"},
    }
    payload.update(changes)
    return payload


def _run_entry(data: bytes):
    return subprocess.run(
        [sys.executable, "-m", "async_rbench.track_b.container_entry"], input=data,
        capture_output=True, cwd=ROOT, timeout=30, env=_test_env(),
    )


def _entry():
    from async_rbench.track_b import container_entry

    return container_entry


def _pid_running(pid: int) -> bool:
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    status = Path(f"/proc/{pid}/stat")
    return not status.exists() or status.read_text().split()[2] != "Z"


def test_supervisor_forwards_bytes_and_preserves_final_output_and_exit(capfdbinary, tmp_path):
    payload = b'{ "kind" : "episode_start" }\r\n{"text":"\xe6\xb5\x8b\xe8\xaf\x95"}\n'
    code = (
        "import pathlib,sys; pathlib.Path(sys.argv[1]).touch(); data=sys.stdin.buffer.read(); "
        "sys.stdout.buffer.write(data); sys.stdout.buffer.flush(); "
        "sys.stderr.write('child diagnostic\\n'); sys.exit(7)"
    )

    ready = tmp_path / "ready"
    with _input_after_child_ready(ready, payload) as (stream, _observed):
        result = _entry()._supervise(
            [sys.executable, "-c", code, str(ready)], stdin=stream,
            env=_test_env(), timeout_sec=20,
        )

    captured = capfdbinary.readouterr()
    assert result == 7
    assert captured.out == payload
    assert captured.err.strip() == b"child diagnostic"


def test_supervisor_returns_child_exit_while_parent_input_is_open(capfdbinary):
    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd, "rb") as stream:
        try:
            result = _entry()._supervise(
                [sys.executable, "-c", "import sys; print('finished', flush=True); sys.exit(9)"],
                stdin=stream, env=_test_env(), timeout_sec=20,
            )
        finally:
            os.close(write_fd)

    assert result == 9
    assert capfdbinary.readouterr().out.strip() == b"finished"


def test_supervisor_stops_child_and_grandchild_after_input_eof(tmp_path):
    report = tmp_path / "processes.json"
    code = (
        "import json, os, pathlib, subprocess, sys, time; "
        "child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps([os.getpid(), child.pid])); "
        "time.sleep(60)"
    )
    with _input_after_child_ready(report) as (stream, observed):
        result = _entry()._supervise(
            [sys.executable, "-c", code, str(report)], stdin=stream,
            env=_test_env(), timeout_sec=20,
        )

    assert result != 0
    assert observed and time.monotonic() - observed[0] < 5
    pids = json.loads(report.read_text())
    assert all(not _pid_running(pid) for pid in pids)


def test_supervisor_timeout_stops_child_even_with_open_input(monkeypatch):
    spawned = []
    real_popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(_entry().subprocess, "Popen", launch)
    read_fd, write_fd = os.pipe()
    started = time.monotonic()
    with os.fdopen(read_fd, "rb") as stream:
        try:
            result = _entry()._supervise(
                [sys.executable, "-c", "import time; time.sleep(60)"], stdin=stream,
                env=_test_env(), timeout_sec=0.5,
            )
        finally:
            os.close(write_fd)

    assert result == 124
    assert time.monotonic() - started < 10
    # The owned process handle remains definitive even if Windows reuses its PID.
    assert spawned[0].poll() is not None


def test_doctor_supervision_waits_for_result_after_input_eof(capfdbinary):
    result = _entry()._supervise(
        [sys.executable, "-c", "import time; time.sleep(1.2); print('doctor result', flush=True)"],
        stdin=io.BytesIO(), env=_test_env(), timeout_sec=20,
        stop_on_eof=False,
    )

    assert result == 0
    assert capfdbinary.readouterr().out.strip() == b"doctor result"


@pytest.mark.skipif(os.name == "nt", reason="Linux process groups and Unix SIGTERM")
@pytest.mark.parametrize("detached", [False, True], ids=["same-session", "detached-session"])
def test_supervisor_sigterm_kills_even_a_term_resistant_grandchild(tmp_path, detached):
    report = tmp_path / "processes.json"
    child_code = (
        "import json, os, pathlib, signal, subprocess, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "child=subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'], "
        f"start_new_session={detached}); "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid])); time.sleep(60)"
    )
    supervisor_code = (
        "import os,sys; from async_rbench.track_b.container_entry import _supervise; "
        "sys.exit(_supervise([sys.executable,'-c',sys.argv[1],sys.argv[2]], "
        "stdin=sys.stdin.buffer, env=dict(os.environ), timeout_sec=20))"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", supervisor_code, child_code, str(report)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT, env=_test_env(),
    )
    try:
        deadline = time.monotonic() + 5
        while not report.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert report.exists()
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 128 + signal.SIGTERM
        assert all(not _pid_running(pid) for pid in json.loads(report.read_text()))
    finally:
        if process.poll() is None:
            process.kill()
        if report.exists():
            for pid in json.loads(report.read_text()):
                if _pid_running(pid):
                    os.kill(pid, signal.SIGKILL)
        process.communicate(timeout=5)


def test_bootstrap_consumes_only_private_first_line():
    bootstrap = _bootstrap(environment={})
    protocol = b'{ "type" : "episode_start" }\r\n{"text":"\xe6\xb5\x8b\xe8\xaf\x95"}\n'
    stream = io.BytesIO(json.dumps(bootstrap).encode() + b"\n" + protocol)

    assert _entry()._read_bootstrap(stream) == bootstrap
    assert stream.read() == protocol


@pytest.mark.parametrize("data", [
    b'{"secret":"private-sentinel",\n',
    b'{"secret":"private-sentinel"}',
    b'[]\n',
    b'{"operation":"adapter","operation":"doctor"}\n',
    b'{"value":NaN}\n',
    b'{"secret":"private-sentinel"' + b" " * (1024 * 1024) + b"}\n",
], ids=["invalid-json", "missing-newline", "non-object", "duplicate-key", "nonfinite", "oversized"])
def test_malformed_bootstrap_fails_without_echoing_private_input(data):
    result = _run_entry(data)

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.strip()
    assert b"private-sentinel" not in result.stderr
    assert b"Traceback" not in result.stderr


@pytest.mark.parametrize("change", [
    {"environment": {"PATH": "private-sentinel"}},
    {"environment": {"UNSELECTED_API_KEY": "private-sentinel"}},
    {"args": ["--config", "private-sentinel"]},
    {"args": ["--workspace-mode", "host"]},
    {"operation": "private-sentinel"},
    {"unexpected": "private-sentinel"},
    {"runtime_metadata": {"image_id": "private-sentinel", "os": "linux"}},
    {"runtime_metadata": {"image_id": "sha256:" + "a" * 64, "os": "windows"}},
    {"runtime_metadata": {"image_id": "sha256:" + "a" * 64, "os": "linux", "secret": "private-sentinel"}},
    {"codex_auth": {"tokens": {"access_token": "private-sentinel"}}},
])
def test_bootstrap_rejects_unselected_credentials_and_argument_or_metadata_injection(change):
    result = _run_entry(json.dumps(_bootstrap(**change)).encode() + b"\n")

    assert result.returncode == 2
    assert result.stdout == b""
    assert b"private-sentinel" not in result.stderr
    assert b"Traceback" not in result.stderr


def test_bootstrap_revalidates_config_and_reserved_credential_names():
    for key, value in (
        ("credential_env", "PYTHON_STARTUP_KEY"),
        ("credential_env", "PATH"),
        ("runtime", {"type": "docker", "image": "fixture", "timeout_sec": 0}),
        ("runtime", {"type": "host"}),
        ("config_sha256", "private-sentinel"),
    ):
        bootstrap = _bootstrap()
        bootstrap["config"][key] = value
        result = _run_entry(json.dumps(bootstrap).encode() + b"\n")
        assert result.returncode == 2
        assert result.stdout == b""
        assert b"private-sentinel" not in result.stderr


def test_private_child_home_contains_only_selected_auth_and_is_removed(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "host-codex-must-not-be-read"))
    monkeypatch.setenv("UNSELECTED_API_KEY", "private-unselected")
    monkeypatch.setenv("PYTHONPATH", "private-host-import-override")
    bootstrap = _bootstrap()
    bootstrap["config"]["framework"] = "codex-cli"
    bootstrap["codex_auth"] = {"auth_mode": "chatgpt", "tokens": {"access_token": "private-saved-token"}}
    bootstrap["args"] = ["--workspace-mode", "container_clone"]

    with _entry()._prepared_child(bootstrap) as child:
        assert child.argv[:3] == [sys.executable, "-m", "async_rbench.track_b.adapter"]
        config_path = Path(child.argv[child.argv.index("--config") + 1])
        assert json.loads(config_path.read_text()) == bootstrap["config"]
        child_home = Path(child.environment["HOME"])
        auth_path = child_home / ".codex" / "auth.json"
        assert json.loads(auth_path.read_text()) == bootstrap["codex_auth"]
        assert Path(child.environment["CODEX_HOME"]) == child_home / ".codex"
        assert list((child_home / ".codex").iterdir()) == [auth_path]
        assert "UNSELECTED_API_KEY" not in child.environment
        assert "PYTHONPATH" not in child.environment
        assert child.environment["ASYNC_RBENCH_AGENT_CONTAINER"] == "1"
        assert json.loads(child.environment["ASYNC_RBENCH_AGENT_RUNTIME_METADATA"]) == bootstrap["runtime_metadata"]
        if os.name != "nt":
            assert stat.S_IMODE(auth_path.stat().st_mode) == 0o600
            assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
            assert stat.S_IMODE(config_path.parent.stat().st_mode) == 0o700

    assert not config_path.exists()
    assert not child_home.exists()
    assert list(tmp_path.iterdir()) == []


def test_selected_credential_reaches_child_and_private_files_wipe_after_error(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    bootstrap = _bootstrap(environment={"PROVIDER_API_KEY": "private-selected-token"})
    bootstrap["config"]["credential_env"] = "PROVIDER_API_KEY"

    with pytest.raises(RuntimeError, match="child failed"):
        with _entry()._prepared_child(bootstrap) as child:
            completed = subprocess.run(
                [sys.executable, "-c", "import os; print(os.environ['PROVIDER_API_KEY'])"],
                env=child.environment, capture_output=True, check=True,
            )
            assert completed.stdout.strip() == b"private-selected-token"
            assert "private-selected-token" not in " ".join(child.argv)
            raise RuntimeError("child failed")
    assert list(tmp_path.iterdir()) == []


def test_entry_runs_actual_deterministic_doctor_after_bootstrap_eof():
    result = _run_entry(json.dumps(_bootstrap(operation="doctor", args=[])).encode() + b"\n")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["framework"] == "deterministic"
    assert report["ready"] is True
    assert result.stderr == b""
