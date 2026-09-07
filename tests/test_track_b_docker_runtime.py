"""Opt-in black-box Docker checks; no model calls or task containers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.container_runtime import doctor_container, remove_owned_container


IMAGE = os.environ.get("TRACK_B_AGENT_TEST_IMAGE")
pytestmark = pytest.mark.skipif(not IMAGE, reason="set TRACK_B_AGENT_TEST_IMAGE for real Docker transport checks")


def _names() -> set[str]:
    result = subprocess.run(
        ["docker", "ps", "--all", "--filter", "label=org.async-rbench.track-b.launch", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=True, timeout=20,
    )
    return set(result.stdout.splitlines())


def _wait_for(check, seconds=35):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError("container lifecycle condition was not reached")


def _config(timeout=30):
    return TrackBConfig(track="B", framework="deterministic", model="fixture",
                        runtime={"type": "docker", "image": IMAGE, "timeout_sec": timeout,
                                 "cpus": 0.5, "memory": "512m"})


def test_doctor_runs_inside_the_selected_linux_image():
    before = _names()
    report = doctor_container(_config())
    assert report["ready"] is True, report
    assert report["runtime"] == "docker"
    assert _names() == before


@pytest.mark.parametrize("ending", ["eof", "timeout", "launcher_killed"])
def test_agent_container_is_removed_when_its_session_ends(tmp_path: Path, ending: str):
    before = _names()
    config = _config(timeout=3 if ending == "timeout" else 60)
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(config._public_payload()), encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "async_rbench.track_b.adapter", "--config", str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    owned = set()
    try:
        owned = _wait_for(lambda: _names() - before)
        assert len(owned) == 1
        if ending == "eof":
            process.stdin.close()
        elif ending == "launcher_killed":
            # On Windows this deliberately kills only the venv launcher; the
            # production parent monitor must release its Docker child as well.
            process.kill()
        process.wait(timeout=40)
        _wait_for(lambda: not (_names() & owned))
        assert _names() == before
    finally:
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=10)
            else:
                process.kill()
            process.wait(timeout=10)
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        for name in owned:
            remove_owned_container(name)
