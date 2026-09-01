#!/usr/bin/env bash
set -uo pipefail
# Private verifier. Runs against a frozen filesystem snapshot of the submitted
# container; the participant never sees this runner or the tests.
pytest -q -rA /async_rbench_tests/test_case_outcomes.py
