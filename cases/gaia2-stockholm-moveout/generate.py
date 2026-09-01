from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from async_rbench.docker_case import export_task
if __name__ == "__main__": export_task(Path(__file__).resolve().parent, "gaia2-stockholm-moveout")
