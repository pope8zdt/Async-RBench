from pathlib import Path
import sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir(): sys.path.insert(0, str(parent)); break
from async_rbench.docker_case import export_task
if __name__ == '__main__': export_task(Path(__file__).resolve().parent, 'osw-dependency-unblock-1a3f65b5b8')
