#!/usr/bin/env bash
set -euo pipefail
cd /app
# Docker snapshots preserve the submitted filesystem but intentionally do not
# preserve participant processes. Recreate the required service from the
# submitted implementation inside the private verifier clone.
if [ -f /app/server.py ]; then
  nohup python /app/server.py >/tmp/async_rbench-verifier-grpc.log 2>&1 &
  for _ in $(seq 1 30); do
    python -c "import socket; s=socket.socket(); s.settimeout(.2); raise SystemExit(0 if s.connect_ex(('127.0.0.1',5328)) == 0 else 1)" && break
    sleep .2
  done
fi
pytest -q -rA /async_rbench_tests/test_case_outcomes.py
