#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/research_proposal.md'); p.write_text(p.read_text().replace('resolution-flexible continuous 2D scanning with pruning-aware hidden-state alignment and token-importance calibration','generic majority vote'))
PY
