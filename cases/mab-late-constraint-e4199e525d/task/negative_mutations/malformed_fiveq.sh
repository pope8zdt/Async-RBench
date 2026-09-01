#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/research_proposal.md');p.write_text(p.read_text().split('**[Question 5]')[0])
PY
