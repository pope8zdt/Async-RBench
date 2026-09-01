"""Regression tests for the shared-daemon-safe OSWorld Dart cleanup path."""

from __future__ import annotations

import ast
import re
import sys
import types
from pathlib import Path

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("upstream/osworld/scripts/python/run_multienv_dart_gui.py")
pytestmark = requires_author_local(
    "upstream/osworld/scripts/python/run_multienv_dart_gui.py",
)


class _Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _Completed:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _cleanup_function(monkeypatch, fake_subprocess):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cleanup = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "cleanup_docker_containers"
    )
    module = ast.Module(body=[cleanup], type_ignores=[])
    namespace = {"List": list, "logger": _Logger(), "re": re}
    monkeypatch.setitem(sys.modules, "subprocess", fake_subprocess)
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace["cleanup_docker_containers"]


def test_cleanup_requires_an_explicit_allowlist(monkeypatch):
    calls = []
    fake_subprocess = types.SimpleNamespace(
        TimeoutExpired=TimeoutError,
        run=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    cleanup = _cleanup_function(monkeypatch, fake_subprocess)

    cleanup()

    assert calls == []


def test_cleanup_never_enumerates_or_removes_an_unrelated_dtb2_container(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["docker", "ps", "-aq"]:
            assert args[3:5] == ["--filter", "name=^/osworld-owned$"]
            return _Completed("0123456789ab\n")
        if args[:3] == ["docker", "rm", "-f"]:
            assert args[3] == "0123456789ab"
            return _Completed()
        raise AssertionError(f"unexpected Docker command: {args}")

    fake_subprocess = types.SimpleNamespace(TimeoutExpired=TimeoutError, run=run)
    cleanup = _cleanup_function(monkeypatch, fake_subprocess)

    cleanup(container_names=["osworld-owned"])

    assert all("dtb2-unrelated" not in " ".join(map(str, call[0])) for call in calls)
    assert all(call[1]["shell"] is False for call in calls)


def test_source_has_no_global_docker_enumeration_or_shell_cleanup():
    source = SOURCE.read_text(encoding="utf-8")

    assert 'docker ps --format "{{.ID}} {{.Names}}"' not in source
    assert "grep -v" not in source
    assert "docker rm -f {container_id}" not in source
    assert '"--cleanup-container"' in source
    assert '"--cleanup-compose-project"' in source
    assert '"--cleanup-label"' in source
