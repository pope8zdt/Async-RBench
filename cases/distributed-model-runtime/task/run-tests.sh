#!/usr/bin/env bash
set -euo pipefail
pytest -q -rA /async_rbench_tests/test_case_outcomes.py
