from __future__ import annotations

from pathlib import Path
import inspect

from types import SimpleNamespace

from async_rbench import docker_case
from async_rbench import cli
from async_rbench.docker_case import _project, cleanup_instance


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


def test_quality_orchestrators_have_outer_compose_cleanup() -> None:
    # Verifier normally performs the down itself. These outer finally blocks
    # cover interruption/failure after Oracle has succeeded but before the
    # verifier process can start.
    declared = inspect.getsource(cli._execute_declared_quality_variants)
    candidate = inspect.getsource(cli.cmd_candidate_quality_preflight)
    assert declared.count("finally:\n            cleanup_instance(case_id, instance)") == 2
    assert candidate.count(
        "finally:\n            cleanup_instance(args.candidate, instance)"
    ) == 2
