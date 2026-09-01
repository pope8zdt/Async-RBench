from pathlib import Path
import sys
for p in Path(__file__).resolve().parents:
    if (p / "async_rbench").is_dir():
        sys.path.insert(0, str(p))
        break
from async_rbench.docker_case import export_task
if __name__ == "__main__":
    export_task(Path(__file__).resolve().parent, "osw-dependency-unblock-346b788fd5")
