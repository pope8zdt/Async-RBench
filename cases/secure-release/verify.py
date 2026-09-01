from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from async_rbench.docker_case import run_verifier
if __name__ == "__main__": run_verifier("secure-release")
