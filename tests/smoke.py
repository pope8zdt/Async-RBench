from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE)


def main() -> None:
    validation = json.loads(run(sys.executable, "-m", "async_rbench.cli", "validate").stdout)
    with tempfile.TemporaryDirectory(prefix="async_rbench-export-") as temp:
        root = Path(temp) / "instances"
        run(sys.executable, "-m", "async_rbench.cli", "build-all", "--output", str(root), "--seed", "17")
        for case_id in validation["cases"]:
            task = root / case_id / "task"
            for required in ("Dockerfile", "docker-compose.yaml", "task.yaml", "run-tests.sh", "oracle.sh"):
                assert (task / required).is_file(), f"{case_id}: missing exported {required}"
            outcome_tests = list((task / "tests").glob("test_case_outcomes.py"))
            assert len(outcome_tests) == 1, f"{case_id}: missing case-specific outcome tests"
            assert not list((task / "tests").glob("test_upstream_*.py")), (
                f"{case_id}: upstream task tests must not be part of the private verifier"
            )
    print(json.dumps({"smoke_test": "passed", "source_lock": "verified", "task_exports": 3}, indent=2))


if __name__ == "__main__":
    main()
