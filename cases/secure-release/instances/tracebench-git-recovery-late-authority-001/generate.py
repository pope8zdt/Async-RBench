from pathlib import Path
import sys

HERE = Path(__file__).resolve()
PROJECT_ROOT = next(parent for parent in HERE.parents if (parent / "async_rbench").is_dir())
sys.path.insert(0, str(PROJECT_ROOT))
from async_rbench.docker_case import export_task

CASE_ID = "secure-release"
if __name__ == "__main__":
    export_task(Path(__file__).resolve().parent, CASE_ID)
