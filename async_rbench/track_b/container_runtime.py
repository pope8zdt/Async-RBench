"""Host-side Docker transport for the existing participant JSONL protocol."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from .config import TrackBConfig


_LABEL = "org.async-rbench.track-b.launch"
_DOCKER_ENV = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "USERPROFILE", "HOME",
    "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "DOCKER_HOST", "DOCKER_CONTEXT",
    "DOCKER_CONFIG", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
}


def docker_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.upper() in _DOCKER_ENV}


def validate_credential_name(name: str) -> None:
    if not name:
        return
    if (
        not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", name)
        or not name.endswith(("_KEY", "_TOKEN", "_SECRET"))
        or name.startswith(("PYTHON", "LD_", "DYLD_", "ASYNC_RBENCH_", "DOCKER_"))
    ):
        raise ValueError("container credential_env must name a provider KEY, TOKEN or SECRET")


def docker_json(*args: str) -> Any:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("Docker CLI is not installed")
    result = subprocess.run(
        [executable, *args], capture_output=True, timeout=30, env=docker_environment(),
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    if result.returncode:
        raise RuntimeError("Docker inspection failed; verify the daemon and selected image")
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("Docker inspection returned invalid metadata") from exc


def inspect_image(image: str) -> dict[str, str]:
    data = docker_json("image", "inspect", image)
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError("runtime image inspection was ambiguous")
    item = data[0]
    if item.get("Os") != "linux":
        raise ValueError("Track B agent runtime requires a Linux image")
    identity = item.get("Id", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
        raise ValueError("runtime image has no immutable identity")
    return {"image_id": identity, "os": "linux"}


def make_bootstrap(
    config: TrackBConfig, adapter_args: list[str], *, image_id: str, operation: str = "adapter",
) -> dict[str, Any]:
    config.validate()
    validate_credential_name(config.credential_env)
    environment = {}
    if config.credential_env and os.environ.get(config.credential_env):
        environment[config.credential_env] = os.environ[config.credential_env]
    payload: dict[str, Any] = {
        "operation": operation, "config": config._public_payload(), "args": adapter_args,
        "environment": environment, "runtime_metadata": {"image_id": image_id, "os": "linux"},
    }
    if config.framework == "codex-cli" and "--conformance" not in adapter_args:
        account_root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        auth_path = account_root / "auth.json"
        if auth_path.is_file():
            try:
                auth = json.loads(auth_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError):
                raise ValueError("saved Codex authentication could not be loaded") from None
            if not isinstance(auth, dict) or not isinstance(auth.get("tokens"), dict):
                raise ValueError("Codex container requires saved ChatGPT authentication")
            # Only the saved account login, not settings, skills or account history.
            payload["codex_auth"] = {
                key: auth[key] for key in ("auth_mode", "tokens", "last_refresh") if key in auth
            }
        elif operation != "doctor":
            raise ValueError("Codex container requires file-backed saved ChatGPT login; run codex login")
    return payload


def build_docker_command(config: TrackBConfig, *, image_id: str, name: str) -> list[str]:
    config.validate_runtime()
    if not re.fullmatch(r"track-b-agent-[0-9a-z]+", name):
        raise ValueError("invalid Track B agent container name")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("agent image must be resolved to an immutable identity")
    options = config.runtime
    return [
        shutil.which("docker") or "docker", "run", "--rm", "--interactive", "--init",
        f"--name={name}", f"--label={_LABEL}={name}",
        "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--user=1000:1000", "--pids-limit=256",
        f"--cpus={options.get('cpus', 0.5)}", f"--memory={options.get('memory', '768m')}",
        f"--memory-swap={options.get('memory', '768m')}",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=134217728,mode=1777",
        "--tmpfs=/home/agent:rw,nosuid,nodev,size=67108864,uid=1000,gid=1000,mode=700",
        "--workdir=/home/agent", "--env=HOME=/home/agent", "--env=SHELL=/bin/bash",
        "--env=PYTHONUNBUFFERED=1", "--env=PYTHONUTF8=1", "--entrypoint=python",
        image_id, "-m", "async_rbench.track_b.container_entry",
    ]


def remove_owned_container(name: str) -> None:
    """Never select containers by a broad prefix, ancestor image or process name."""
    try:
        items = docker_json("container", "inspect", name)
        if not isinstance(items, list) or len(items) != 1:
            return
        item = items[0]
        if (item.get("Config", {}).get("Labels") or {}).get(_LABEL) != name:
            return
        identity = item.get("Id", "")
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            return
        subprocess.run(
            [shutil.which("docker") or "docker", "rm", "--force", identity],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
            env=docker_environment(),
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return


async def _run(
    config: TrackBConfig, adapter_args: list[str], *, operation: str,
) -> tuple[int, bytes]:
    metadata = await asyncio.to_thread(inspect_image, config.runtime["image"])
    bootstrap = make_bootstrap(config, adapter_args, image_id=metadata["image_id"], operation=operation)
    name = "track-b-agent-" + uuid.uuid4().hex
    command = build_docker_command(config, image_id=metadata["image_id"], name=name)
    from .frameworks.codex_cli import protect_process, terminate_process
    process = await asyncio.create_subprocess_exec(
        *command, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE if operation == "doctor" else None,
        stderr=asyncio.subprocess.DEVNULL, env=docker_environment(),
        **({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
           if os.name == "nt" else {"start_new_session": True}),
    )
    guard = None
    loop = asyncio.get_running_loop()
    try:
        guard = protect_process(process)
        assert process.stdin is not None
        process.stdin.write((json.dumps(bootstrap, ensure_ascii=False) + "\n").encode("utf-8"))
        await process.stdin.drain()
        # Discard the host copy after transferring the private bootstrap.
        del bootstrap
        if operation == "doctor":
            process.stdin.close()
            output, _ = await asyncio.wait_for(process.communicate(), timeout=90)
            return int(process.returncode), output

        async def send(line: bytes) -> None:
            if process.stdin and not process.stdin.is_closing():
                process.stdin.write(line)
                await process.stdin.drain()

        def pump() -> None:
            try:
                # A daemon blocked on BufferedReader's lock can prevent Python
                # shutdown after the remote worker has already finished.
                stream = getattr(sys.stdin.buffer, "raw", sys.stdin.buffer)
                while chunk := stream.read(65536):
                    asyncio.run_coroutine_threadsafe(send(chunk), loop).result()
            except (BrokenPipeError, ConnectionError, RuntimeError):
                pass
            finally:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(process.stdin.close)

        threading.Thread(target=pump, name="track-b-container-stdin", daemon=True).start()
        code = await asyncio.wait_for(process.wait(), timeout=config.runtime.get("timeout_sec", 2400) + 30)
        return int(code), b""
    except asyncio.TimeoutError:
        raise RuntimeError("Track B agent container exceeded its runtime timeout") from None
    finally:
        try:
            if process.returncode is None:
                await terminate_process(process)
        finally:
            if guard is not None:
                guard.close()
            await asyncio.to_thread(remove_owned_container, name)


def run_container_adapter(config: TrackBConfig, adapter_args: list[str]) -> int:
    code, _ = asyncio.run(_run(config, adapter_args, operation="adapter"))
    if code:
        print(f"Track B agent container exited with status {code}", file=sys.stderr)
    return code


def doctor_container(config: TrackBConfig) -> dict[str, Any]:
    try:
        code, output = asyncio.run(_run(config, [], operation="doctor"))
        report = json.loads(output)
        if not isinstance(report, dict) or report.get("framework") != config.framework:
            raise ValueError("invalid container doctor response")
        report["ready"] = code == 0 and report.get("ready") is True
        report["runtime"] = "docker"
        return report
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        return {"framework": config.framework, "ready": False, "runtime": "docker",
                "detail": "Container doctor failed; check the local Linux image, Docker and selected credentials"}
