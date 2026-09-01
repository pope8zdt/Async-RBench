from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from async_rbench.private_eval import audit_participant_container, run_isolated_verifier


pytestmark = pytest.mark.docker


@pytest.mark.skipif(os.getenv("ASYNC_RBENCH_RUN_DOCKER_TESTS") != "1", reason="opt-in Docker mutation test")
def test_hidden_verifier_bundle_exists_only_in_private_clone(tmp_path: Path) -> None:
    suffix = uuid.uuid4().hex[:10]
    participant = f"dtb2-private-eval-test-{suffix}"
    task = tmp_path / "task"
    tests = task / "tests"
    tests.mkdir(parents=True)
    (tests / "sentinel.txt").write_text("private-sentinel", encoding="utf-8")
    runner = task / "run-tests.sh"
    runner.write_text(
        "#!/bin/sh\nset -eu\ntest \"$(cat /async_rbench_tests/sentinel.txt)\" = private-sentinel\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["docker", "run", "-d", "--name", participant, "ubuntu:24.04", "sleep", "300"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        # Strict startup audit proves the task image itself did not leak tests.
        audit_participant_container(participant)
        # Agents are allowed to create their own conventional /tests path.
        subprocess.run(
            ["docker", "exec", participant, "mkdir", "-p", "/tests"], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        subprocess.run(
            ["docker", "exec", participant, "/bin/sh", "-c", "printf participant > /tests/participant.txt"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        result = run_isolated_verifier(
            main_container=participant, task_dir=task, episode_id=f"private-test-{suffix}", timeout_sec=30,
        )
        assert result.success
        absent = subprocess.run(
            ["docker", "exec", participant, "test", "!", "-e", "/async_rbench_tests"],
            check=False,
        )
        assert absent.returncode == 0
        participant_tests_untouched = subprocess.run(
            ["docker", "exec", participant, "/bin/sh", "-c", "test \"$(cat /tests/participant.txt)\" = participant"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert participant_tests_untouched.returncode == 0
    finally:
        subprocess.run(
            ["docker", "rm", "-f", participant], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
