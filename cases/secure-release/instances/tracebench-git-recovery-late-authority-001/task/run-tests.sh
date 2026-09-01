#!/usr/bin/env bash
set -uo pipefail
# The private verifier runs from a filesystem snapshot. Start services from the
# participant-produced configuration; do not carry participant processes into
# the verifier security boundary.
rm -f /run/nginx.pid /run/sshd.pid
mkdir -p /run/sshd
/usr/sbin/sshd || printf '%s\n' 'ASYNC_RBENCH_SERVICE_START sshd failed'
nginx || printf '%s\n' 'ASYNC_RBENCH_SERVICE_START nginx failed'
# The submitted bare repository is correctly owned by the service account
# `git`, while the private verifier runs as root. Trust only the two exact
# repositories under evaluation so Git's ownership guard does not turn a
# correct deployment into an evaluator-environment failure.
git config --global --add safe.directory /app/repo
git config --global --add safe.directory /git/project.git

overall_status=0
run_component() {
  local component="$1"
  shift
  local status
  printf 'ASYNC_RBENCH_COMPONENT_BEGIN %s\n' "$component"
  "$@"
  status=$?
  printf 'ASYNC_RBENCH_COMPONENT_END %s exit_code=%s\n' "$component" "$status"
  if [ "$status" -ne 0 ]; then
    overall_status=1
  fi
}

# Execute categories independently so one broken service does not prevent
# pytest outcomes from being emitted for unrelated frozen semantic points.
run_component authority pytest -q -rA /async_rbench_tests/test_case_outcomes.py -k authority
run_component stale_exclusion pytest -q -rA /async_rbench_tests/test_case_outcomes.py -k stale
run_component downstream_rebuild pytest -q -rA /async_rbench_tests/test_case_outcomes.py -k downstream
run_component runtime_behavior pytest -q -rA /async_rbench_tests/test_case_outcomes.py -k runtime
run_component lineage_reverification pytest -q -rA /async_rbench_tests/test_case_outcomes.py -k lineage
run_component independent_preservation pytest -q -rA /async_rbench_tests/test_case_outcomes.py -k support

exit "$overall_status"
