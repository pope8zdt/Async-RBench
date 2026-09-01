"""Run the architecture validation and protocol-3 regression suite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    validate = subprocess.run(
        [sys.executable, "-m", "async_rbench.cli", "validate"], cwd=ROOT,
        check=False,
    )
    if validate.returncode:
        return int(validate.returncode)
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=ROOT, check=False,
    )
    return int(tests.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
