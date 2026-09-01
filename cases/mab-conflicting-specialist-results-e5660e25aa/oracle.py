from pathlib import Path
import sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0, str(parent)); break
from async_rbench.docker_case import run_oracle
if __name__ == '__main__': run_oracle('mab-conflicting-specialist-results-e5660e25aa')
