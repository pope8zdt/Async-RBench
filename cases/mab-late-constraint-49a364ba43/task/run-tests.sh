#!/bin/bash
set -euo pipefail
cd /async_rbench_tests
test_files=(test_case_outcomes.py test_control_flow.py)
if [[ -f upstream_tests/test_outputs.py ]]; then test_files=(upstream_tests/test_outputs.py "${test_files[@]}"); fi
python3 -m pytest -q -rA "${test_files[@]}"
