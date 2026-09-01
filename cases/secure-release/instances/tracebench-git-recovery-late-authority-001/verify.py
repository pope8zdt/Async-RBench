from pathlib import Path
import sys

HERE = Path(__file__).resolve()
PROJECT_ROOT = next(parent for parent in HERE.parents if (parent / "async_rbench").is_dir())
sys.path.insert(0, str(PROJECT_ROOT))
from async_rbench.docker_case import run_verifier

CASE_ID = "secure-release"
if __name__ == "__main__":
    run_verifier(CASE_ID)
