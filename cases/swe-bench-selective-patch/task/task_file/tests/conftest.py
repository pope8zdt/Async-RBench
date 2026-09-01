"""Make the trimmed sklearn package importable when pytest runs these tests.

The package under test lives at /app/task_file/src/sklearn. The fix target is
``sklearn/utils/multiclass.py``; tests import ``sklearn.metrics``,
``sklearn.preprocessing`` and ``sklearn.utils.multiclass`` and therefore need
``src`` on ``sys.path`` before collection.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
