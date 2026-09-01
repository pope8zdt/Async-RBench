#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); old="self.messages.append(row); return row"; assert old in t; p.write_text(t.replace(old,"return row"))
PY
