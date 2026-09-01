#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/research_proposal.md');p.write_text(p.read_text().replace('risk-calibrated hierarchical skill selection with online opponent adaptation and confidence-aware fallback','generic fixed skill selection'))
PY
