"""Private bootstrap and bounded child supervision inside a Track B container."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from .config import TrackBConfig
from .container_runtime import validate_credential_name


_EOF_GRACE_SEC = 1.0
_TERM_GRACE_SEC = 0.5
_MAX_BOOTSTRAP_BYTES = 1024 * 1024
_CONTAINER_ENV = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SHELL", "LANG", "LC_ALL",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate bootstrap field")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise ValueError("non-finite bootstrap value")


def _read_bootstrap(stdin: BinaryIO) -> dict[str, Any]:
    line = stdin.readline(_MAX_BOOTSTRAP_BYTES + 1)
    if len(line) > _MAX_BOOTSTRAP_BYTES or not line.endswith(b"\n"):
        raise ValueError("invalid bootstrap framing")
    payload = json.loads(
        line.decode("utf-8"), object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("bootstrap must be an object")
    return payload


def _validate_bootstrap(payload: dict[str, Any]) -> None:
    required = {"operation", "config", "args", "environment", "runtime_metadata"}
    if set(payload) - required - {"codex_auth"} or not required <= set(payload):
        raise ValueError("invalid bootstrap fields")
    operation = payload["operation"]
    if operation not in ("adapter", "doctor"):
        raise ValueError("invalid bootstrap operation")
    config = payload["config"]
    if not isinstance(config, dict):
        raise ValueError("invalid bootstrap configuration")
    for name in ("track", "framework", "model", "credential_env"):
        if name in config and not isinstance(config[name], str):
            raise ValueError("invalid bootstrap configuration field")
    for name in ("components", "limits", "framework_options", "runtime"):
        if name in config and not isinstance(config[name], dict):
            raise ValueError("invalid bootstrap configuration field")
    if config.get("runtime", {}).get("type") != "docker":
        raise ValueError("bootstrap requires the Docker runtime")
    credential = config.get("credential_env", "")
    validate_credential_name(credential)
    environment = payload["environment"]
    if not isinstance(environment, dict) or set(environment) - ({credential} if credential else set()):
        raise ValueError("bootstrap environment contains unselected variables")
    if any(not isinstance(value, str) or "\0" in value for value in environment.values()):
        raise ValueError("invalid bootstrap credential value")
    args = payload["args"]
    choices = [[], ["--conformance"]]
    for mode in ("container_clone", "disabled"):
        choices.extend([
            ["--workspace-mode", mode], ["--conformance", "--workspace-mode", mode],
        ])
    if args not in ([[]] if operation == "doctor" else choices):
        raise ValueError("unsupported bootstrap arguments")
    metadata = payload["runtime_metadata"]
    if (
        not isinstance(metadata, dict) or set(metadata) != {"image_id", "os"}
        or metadata.get("os") != "linux"
        or not isinstance(metadata.get("image_id"), str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", metadata["image_id"])
    ):
        raise ValueError("invalid runtime metadata")
    if "codex_auth" in payload:
        auth = payload["codex_auth"]
        if (
            config.get("framework") != "codex-cli" or not isinstance(auth, dict)
            or set(auth) - {"auth_mode", "tokens", "last_refresh"}
            or not isinstance(auth.get("tokens"), dict)
            or auth.get("auth_mode", "chatgpt") != "chatgpt"
        ):
            raise ValueError("invalid saved account authentication")


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class _PreparedChild:
    argv: list[str]
    environment: dict[str, str]
    timeout_sec: float
    stop_on_eof: bool


@contextmanager
def _prepared_child(bootstrap: dict[str, Any]) -> Iterator[_PreparedChild]:
    _validate_bootstrap(bootstrap)
    with tempfile.TemporaryDirectory(prefix="async-rbench-agent-") as temporary:
        directory = Path(temporary)
        os.chmod(directory, 0o700)
        config_path = directory / "config.json"
        _write_private_json(config_path, bootstrap["config"])
        config = TrackBConfig.from_file(config_path)
        child_home = directory / "home"
        child_home.mkdir(mode=0o700)
        codex_home = child_home / ".codex"
        codex_home.mkdir(mode=0o700)
        scratch = directory / "tmp"
        scratch.mkdir(mode=0o700)
        if "codex_auth" in bootstrap:
            _write_private_json(codex_home / "auth.json", bootstrap["codex_auth"])
        environment = {
            key: value for key, value in os.environ.items() if key.upper() in _CONTAINER_ENV
        }
        environment.update({
            "HOME": str(child_home), "USERPROFILE": str(child_home), "CODEX_HOME": str(codex_home),
            "TMP": str(scratch), "TEMP": str(scratch), "TMPDIR": str(scratch),
            "XDG_CONFIG_HOME": str(child_home / ".config"),
            "XDG_CACHE_HOME": str(child_home / ".cache"),
            "XDG_DATA_HOME": str(child_home / ".local" / "share"),
            "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1",
            "ASYNC_RBENCH_AGENT_CONTAINER": "1",
            "ASYNC_RBENCH_AGENT_RUNTIME_METADATA": json.dumps(bootstrap["runtime_metadata"], sort_keys=True),
            **bootstrap["environment"],
        })
        doctor = bootstrap["operation"] == "doctor"
        argv = [sys.executable, "-m"]
        argv.extend(["async_rbench.track_b", "doctor"] if doctor else ["async_rbench.track_b.adapter"])
        argv.extend(["--config", str(config_path), *bootstrap["args"]])
        yield _PreparedChild(
            argv=argv, environment=environment,
            timeout_sec=float(config.runtime.get("timeout_sec", 2400)), stop_on_eof=not doctor,
        )


class _LinuxChildren:
    """Keep detached framework sessions owned by this dedicated supervisor."""

    def __init__(self) -> None:
        import ctypes

        self._libc = ctypes.CDLL(None, use_errno=True)
        self._previous = ctypes.c_int()
        if self._libc.prctl(37, ctypes.byref(self._previous), 0, 0, 0):
            raise OSError("could not inspect child subreaper")
        if self._libc.prctl(36, 1, 0, 0, 0):
            raise OSError("could not enable child subreaper")
        self._baseline = set(self._snapshot())
        self.root: int | None = None
        self.owned: dict[int, str] = {}

    @staticmethod
    def _snapshot() -> dict[int, tuple[int, str, str]]:
        processes = {}
        for directory in Path("/proc").iterdir():
            if not directory.name.isdecimal():
                continue
            try:
                # The process name can contain spaces and closing parentheses.
                fields = (directory / "stat").read_text().rpartition(") ")[2].split()
                processes[int(directory.name)] = (int(fields[1]), fields[19], fields[0])
            except (OSError, ValueError, IndexError):
                continue
        return processes

    def collect(self) -> dict[int, tuple[int, str, str]]:
        processes = self._snapshot()
        selected = {pid for pid, birth in self.owned.items() if processes.get(pid, (0, "", ""))[1] == birth}
        if self.root is not None and self.root in processes:
            selected.add(self.root)
        # Orphans of our child reparent here, including a new-session child whose
        # immediate parent exited before the next scan. Existing processes are
        # excluded; this supervisor does not adopt another caller's old tree.
        selected.update(
            pid for pid, (parent, _birth, _state) in processes.items()
            if parent == os.getpid() and pid not in self._baseline
        )
        while True:
            descendants = {pid for pid, (parent, _birth, _state) in processes.items() if parent in selected}
            added = descendants - selected
            if not added:
                break
            selected.update(added)
        self.owned.update({pid: processes[pid][1] for pid in selected})
        return processes

    def signal(self, signum: int) -> None:
        processes = self.collect()
        for pid, birth in self.owned.items():
            if pid == self.root or processes.get(pid, (0, "", ""))[1] != birth:
                continue
            try:
                os.kill(pid, signum)
            except ProcessLookupError:
                pass

    def reap(self) -> None:
        for pid in self.owned:
            if pid != self.root:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    def live(self) -> bool:
        processes = self.collect()
        return any(
            processes.get(pid, (0, "", "Z"))[1] == birth and processes[pid][2] != "Z"
            for pid, birth in self.owned.items()
        )

    def close(self) -> None:
        self.reap()
        self._libc.prctl(36, self._previous.value, 0, 0, 0)


def _stop_process_group(process: subprocess.Popen[bytes], children: _LinuxChildren | None = None) -> None:
    if os.name == "nt":
        if process.poll() is None:
            process.kill()
    else:
        if children is not None:
            children.signal(signal.SIGTERM)
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        else:
            # The group can outlive its leader; always escalate after the grace.
            deadline = time.monotonic() + _TERM_GRACE_SEC
            while time.monotonic() < deadline:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if children is not None:
            deadline = time.monotonic() + 2
            while True:
                children.signal(signal.SIGKILL)
                children.reap()
                if not children.live() or time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _supervise(
    argv: list[str], *, stdin: BinaryIO, env: dict[str, str], timeout_sec: float,
    stop_on_eof: bool = True,
) -> int:
    """Relay protocol bytes and own the child group until it has fully stopped."""
    stop = threading.Event()
    eof = threading.Event()
    received_signal: list[int] = []
    prior_handlers = {}

    def on_signal(signum: int, _frame: object) -> None:
        received_signal.append(signum)
        stop.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT):
            prior_handlers[signum] = signal.signal(signum, on_signal)

    process = None
    guard = None
    children = None
    try:
        deadline = time.monotonic() + timeout_sec
        if sys.platform == "linux":
            children = _LinuxChildren()
        process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, env=env, bufsize=0,
            **({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == "nt" else {"start_new_session": True}),
        )
        if children is not None:
            children.root = process.pid
        if os.name == "nt":
            from .frameworks.codex_cli import protect_process

            guard = protect_process(process)

        def forward_input() -> None:
            assert process is not None and process.stdin is not None
            # Buffered stdin holds an interpreter lock during a blocking read;
            # a daemon owning that lock aborts Python on EOF/timeout/SIGTERM exit.
            source = getattr(stdin, "raw", stdin)
            read = getattr(source, "read1", source.read)
            try:
                while not stop.is_set():
                    chunk = read(65536)
                    if not chunk:
                        break
                    pending = memoryview(chunk)
                    while pending and not stop.is_set():
                        written = process.stdin.write(pending)
                        if not written:
                            return
                        pending = pending[written:]
            except (OSError, ValueError):
                pass
            finally:
                try:
                    process.stdin.close()
                except OSError:
                    pass
                eof.set()

        threading.Thread(target=forward_input, daemon=True, name="track-b-container-input").start()
        eof_deadline = None
        while True:
            if children is not None:
                children.collect()
            returncode = process.poll()
            if returncode is not None:
                return returncode
            if received_signal:
                return 128 + received_signal[0]
            now = time.monotonic()
            if now >= deadline:
                return 124
            if stop_on_eof and eof.is_set():
                # Close stdin first and let a final episode_ended/normal exit drain.
                if eof_deadline is None:
                    eof_deadline = now + _EOF_GRACE_SEC
                elif now >= eof_deadline:
                    return 1
            stop.wait(0.02)
    finally:
        stop.set()
        try:
            if guard is not None:
                guard.close()
            if process is not None:
                _stop_process_group(process, children)
                if process.stdin is not None:
                    process.stdin.close()
        finally:
            if children is not None:
                children.close()
            for signum, handler in prior_handlers.items():
                signal.signal(signum, handler)


def main() -> int:
    try:
        # Use one raw stream for both phases so bootstrap read-ahead cannot
        # swallow the first participant message or leave a buffered reader lock.
        source = getattr(sys.stdin.buffer, "raw", sys.stdin.buffer)
        bootstrap = _read_bootstrap(source)
        with _prepared_child(bootstrap) as child:
            return _supervise(
                child.argv, stdin=source, env=child.environment,
                timeout_sec=child.timeout_sec, stop_on_eof=child.stop_on_eof,
            )
    except Exception:
        # Config/auth content and exception messages can contain credentials.
        print("Track B container bootstrap or supervisor failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
