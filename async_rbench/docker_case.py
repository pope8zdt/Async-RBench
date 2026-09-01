from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from .private_eval import inject_oracle, remove_oracle, run_isolated_verifier


NETWORK_OVERRIDE = Path(__file__).with_name("docker-compose.network.yaml")


def _project(case_id: str, instance: Path) -> str:
    """Return an instance-isolated Compose project name.

    A family-only name lets concurrent preflights for two instances recreate
    the same container.  The resolved instance path is evaluator-owned and
    stable for the lifetime of a run, so a short digest provides isolation
    without exposing participant data or exceeding Compose name limits.
    """
    stem = case_id.replace("_", "-")[:40]
    identity = str(instance.resolve()).replace("\\", "/").lower().encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:12]
    return f"dtb2-{stem}-{digest}"


def export_task(case_dir: Path, case_id: str) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        def make_writable(function, path, excinfo):
            os.chmod(path, stat.S_IWRITE)
            function(path)
        # ``onexc`` was added to ``shutil.rmtree`` in Python 3.12; earlier
        # interpreters use the deprecated ``onerror``. The callback ignores
        # ``excinfo`` so the same function works for either signature.
        kwargs = (
            {"onexc": make_writable} if sys.version_info >= (3, 12)
            else {"onerror": make_writable}
        )
        shutil.rmtree(output, **kwargs)
    shutil.copytree(case_dir / "task", output / "task")
    (output / "instance.json").write_text(
        json.dumps({"case_id": case_id, "seed": args.seed, "format": "terminal-bench-docker"}, indent=2),
        encoding="utf-8",
    )


def _compose(instance: Path, case_id: str, *args: str, check: bool = True):
    task = instance / "task"
    command = [
        "docker", "compose", "-p", _project(case_id, instance),
        "-f", str(task / "docker-compose.yaml"),
        # All official evaluation packages expose a single `client` service.
        # Reuse Docker's built-in bridge instead of allocating one subnet per
        # short-lived verifier variant; otherwise a large concurrent corpus can
        # exhaust Docker Desktop's predefined address pools.
        "-f", str(NETWORK_OVERRIDE), *args,
    ]
    return subprocess.run(
        command, cwd=task, check=check, text=True,
        encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def cleanup_instance(case_id: str, instance: Path) -> None:
    """Best-effort removal of one evaluator-owned Compose project.

    Oracle intentionally keeps a successful container alive for the hidden
    verifier.  Callers that orchestrate that two-process hand-off must invoke
    this in a ``finally`` block so interruption between the two processes
    cannot leak a project network.
    """
    try:
        _compose(
            instance.resolve(), case_id, "down", "--volumes", "--remove-orphans",
            check=False,
        )
    except OSError:
        # Cleanup is best effort (for example Docker may already be stopped),
        # and must not replace the evaluator's original failure.
        pass


def run_oracle(case_id: str) -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--instance", required=True)
    args = parser.parse_args(); instance = Path(args.instance).resolve()
    started = False
    container = ""
    try:
        up = _compose(instance, case_id, "up", "-d", "--build", check=False)
        print(up.stdout)
        if up.returncode != 0:
            raise RuntimeError(
                f"docker compose up failed with exit {up.returncode}:\n{up.stdout[-8000:]}"
            )
        started = True
        container = _compose(instance, case_id, "ps", "-q", "client").stdout.strip()
        if not container:
            raise RuntimeError("oracle maintenance container is not running")
        inject_oracle(container, instance / "task")
        result = subprocess.run(
            ["docker", "exec", container, "/bin/bash", "/async_rbench/oracle.sh"],
            check=False, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        print(result.stdout)
        if result.returncode != 0:
            raise SystemExit(result.returncode)
    finally:
        if container:
            remove_oracle(container)
        # A failed Oracle never reaches run_verifier, so it must release its
        # exact Compose project here. Successful runs stay alive for verifier.
        if not started or "result" not in locals() or result.returncode != 0:
            cleanup_instance(case_id, instance)


def run_solution_script(
    case_id: str, instance: Path, solution_path: Path, *, fresh: bool = True,
) -> None:
    """Run one evaluator-owned equivalence solution in a fresh task container."""
    instance = instance.resolve()
    solution_path = solution_path.resolve()
    if not solution_path.is_file() or solution_path.suffix != ".sh":
        raise FileNotFoundError(solution_path)
    if fresh:
        print(_compose(
            instance, case_id, "up", "-d", "--build", "--force-recreate",
        ).stdout)
    container = _compose(instance, case_id, "ps", "-q", "client").stdout.strip()
    if not container:
        raise RuntimeError("equivalence-solution container is not running")
    target = "/async_rbench/equivalence-solution.sh"
    _docker_command = ["docker", "exec", container, "mkdir", "-p", "/async_rbench"]
    subprocess.run(_docker_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    subprocess.run(
        ["docker", "cp", str(solution_path), f"{container}:{target}"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    # Equivalence scripts are evaluator-owned.  When a case declares frozen
    # native-evaluator fixtures, expose only that fixture directory under the
    # evaluator mount; it never enters the participant-visible task image.
    evaluator_source = instance / "task" / "upstream_solutions"
    fixture_source = evaluator_source / "fixtures"
    helper_names = (
        "alternative_solution.py", "event_worker.py", "write_manifest.py",
        "alternative_parallel_linear.py", "alternative_pipeline_parallel.py",
    )
    helper_sources = [evaluator_source / name for name in helper_names]
    helper_sources.extend(sorted(evaluator_source.glob("*.sh")))
    helper_sources = list(dict.fromkeys(helper_sources))
    if fixture_source.is_dir() or any(path.is_file() for path in helper_sources):
        subprocess.run(
            ["docker", "exec", container, "mkdir", "-p", "/async_rbench/upstream_solutions"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    if fixture_source.is_dir():
        subprocess.run(
            ["docker", "cp", str(fixture_source),
             f"{container}:/async_rbench/upstream_solutions/fixtures"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    for helper_source in helper_sources:
        if helper_source.is_file():
            subprocess.run(
                ["docker", "cp", str(helper_source),
                 f"{container}:/async_rbench/upstream_solutions/{helper_source.name}"],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
    try:
        subprocess.run(
            ["docker", "exec", container, "sed", "-i", r"s/\r$//", target],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        subprocess.run(
            ["docker", "exec", container, "chmod", "0555", target],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        result = subprocess.run(
            ["docker", "exec", container, "/bin/bash", target],
            check=False, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        print(result.stdout)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout)
    finally:
        subprocess.run(
            ["docker", "exec", container, "rm", "-f", target],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        subprocess.run(
            ["docker", "exec", container, "rm", "-rf", "/async_rbench/upstream_solutions"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )


def run_verifier(case_id: str) -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--instance", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args(); instance = Path(args.instance).resolve()
    try:
        container = _compose(instance, case_id, "ps", "-q", "client").stdout.strip()
        if not container:
            raise RuntimeError("case container is not running")
        result = run_isolated_verifier(
            main_container=container,
            task_dir=instance / "task",
            episode_id=f"oracle-check-{case_id}",
        )
        report = {
            "case_id": case_id,
            "success": result.success,
            "exit_code": result.exit_code,
            "test_output": result.output,
            "verifier_isolation": result.isolation,
            "verifier_bundle_sha256": result.verifier_bundle_sha256,
        }
        output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(result.output)
        raise SystemExit(0 if report["success"] else 1)
    finally:
        cleanup_instance(case_id, instance)
