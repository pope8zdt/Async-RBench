#!/bin/bash
set -euo pipefail
cd /async_rbench_tests
python3 -m pytest -q -rA upstream_tests/test_outputs.py test_case_outcomes.py test_control_flow.py

