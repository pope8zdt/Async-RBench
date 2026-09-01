#!/bin/bash
set -euo pipefail
if [[ -s /async_rbench_tests/source_test.patch ]]; then
  cd /testbed
  if ! git apply --reverse --check /async_rbench_tests/source_test.patch >/dev/null 2>&1; then git apply /async_rbench_tests/source_test.patch; fi
fi
cd /async_rbench_tests
test_files=(test_case_outcomes.py test_control_flow.py)
if [[ -f upstream_tests/test_outputs.py ]]; then test_files=(upstream_tests/test_outputs.py "${test_files[@]}"); fi
python3 -m pytest -q -rA "${test_files[@]}"
