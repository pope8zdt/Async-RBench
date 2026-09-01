#!/usr/bin/env bash
set -uo pipefail
pytest -q -rA /async_rbench_tests/test_case_outcomes.py
