import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASE = "mab-conflicting-specialist-results-5f19377089"


def test_log_aggregation_inputs_are_in_the_public_package():
    logs = ROOT / "data/async-rbench/cases/mab-dependency-unblock-18d7c09304/task/logs"
    assert {p.name for p in logs.glob("*.log")} == {"app1.log", "app2.log", "db.log"}
    assert all(len(p.read_text().splitlines()) == 5 for p in logs.glob("*.log"))


@pytest.mark.docker
@pytest.mark.skipif(os.getenv("ASYNC_RBENCH_RUN_DOCKER_TESTS") != "1", reason="opt-in Docker fixture test")
def test_packaging_task_has_every_declared_input_in_linux_image():
    suffix = uuid.uuid4().hex[:12]
    image = "arbench-fixtures-" + suffix
    task = ROOT / "data/async-rbench/cases" / CASE / "task"
    subprocess.run(["docker", "build", "-t", image, str(task)], check=True, capture_output=True)
    code = (
        "from pathlib import Path; import json; r=Path('/app/task_file'); "
        "m=json.loads((r/'source_manifest.json').read_text()); "
        "assert all((r/'src'/p).exists() or (r/'src'/p).is_symlink() for p in m['included']+m['excluded']); "
        "assert (r/'src/link-out').readlink()==Path('/outside/target'); "
        "assert (r/'src/keys/private.key').stat().st_mode & 0o777 == 0o600"
    )
    try:
        result = subprocess.run(["docker", "run", "--rm", image, "python3", "-c", code], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        subprocess.run(["docker", "image", "rm", image], check=False, capture_output=True)
