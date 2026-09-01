#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path('/app/output_data/solution.py'); text=p.read_text(); old='self.contract=dict(contract); return self.contract'; new="self.contract=None; return self.contract"; assert old in text; p.write_text(text.replace(old,new,1))
PY
