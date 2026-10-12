from __future__ import annotations

from pathlib import Path

from types import SimpleNamespace

from async_rbench import docker_case
from async_rbench.docker_case import _project, cleanup_instance
from async_rbench.evaluation import runner


def test_compose_project_name_is_stable_and_instance_isolated(tmp_path: Path) -> None:
    first = tmp_path / "family" / "instance-a"
    second = tmp_path / "family" / "instance-b"

    assert _project("same_case", first) == _project("same_case", first)
    assert _project("same_case", first) != _project("same_case", second)
    assert _project("same_case", first).startswith("dtb2-same-case-")
    assert len(_project("x" * 100, first)) <= 63


def test_compose_reuses_builtin_bridge_network(tmp_path: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        docker_case.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or SimpleNamespace(returncode=0, stdout=""),
    )

    docker_case._compose(tmp_path, "case-a", "ps")

    command = calls[0][0]
    assert command.count("-f") == 2
    assert str(docker_case.NETWORK_OVERRIDE) in command
    assert docker_case.NETWORK_OVERRIDE.read_text(encoding="utf-8") == (
        "services:\n  client:\n    network_mode: bridge\n"
    )


def test_cleanup_instance_always_downs_exact_project(tmp_path: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        docker_case,
        "_compose",
        lambda instance, case_id, *args, **kwargs: calls.append(
            (instance, case_id, args, kwargs)
        ) or SimpleNamespace(returncode=0, stdout=""),
    )

    cleanup_instance("case-a", tmp_path / "instance")

    assert calls == [(
        (tmp_path / "instance").resolve(),
        "case-a",
        ("down", "--volumes", "--remove-orphans"),
        {"check": False},
    )]


def test_cleanup_instance_does_not_mask_docker_unavailable(tmp_path: Path, monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(docker_case, "_compose", unavailable)
    cleanup_instance("case-a", tmp_path / "instance")


def test_participant_start_uses_declared_compose_command(tmp_path, monkeypatch):
    task = tmp_path / "task"
    task.mkdir()
    (task / "docker-compose.yaml").write_text(
        'services:\n  client:\n    command: [sh, -c, "mkdir -p /app/output_data && sleep infinity"]\n',
        encoding="utf-8")
    calls = []
    monkeypatch.setattr(runner, "_docker", lambda *args, **kwargs:
                        calls.append(args) or SimpleNamespace(stdout="sha256:image", returncode=0))
    runner._prepare_container(tmp_path, "case", "seed-1", "smoke", False, "0123", tmp_path)
    command = next(c for c in calls if c[0] == "run")
    assert command[-3:] == ("sh", "-c", "mkdir -p /app/output_data && sleep infinity")


def test_protocol_only_cleanup_never_requires_docker(monkeypatch):
    def unavailable(*args, **kwargs):
        raise AssertionError("protocol-only conformance must not invoke Docker")
    monkeypatch.setattr(runner, "_docker", unavailable)
    runner._cleanup_workspace_resources("0123", use_container=False)
