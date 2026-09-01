from pathlib import Path
import sys
for p in Path(__file__).resolve().parents:
    if (p / "async_rbench").is_dir():
        sys.path.insert(0, str(p))
        break
from async_rbench.docker_case import run_verifier
if __name__ == "__main__":
    run_verifier("osw-dependency-unblock-346b788fd5")
