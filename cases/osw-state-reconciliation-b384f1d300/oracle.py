from pathlib import Path
import sys
for p in Path(__file__).resolve().parents:
    if (p/'async_rbench').is_dir(): sys.path.insert(0,str(p)); break
from async_rbench.docker_case import run_oracle
if __name__=='__main__': run_oracle("osw-state-reconciliation-b384f1d300")

