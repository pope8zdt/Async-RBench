#!/usr/bin/env bash
set -euo pipefail

work=/tmp/dtb2-authoritative-baseline
rm -rf "$work"
git clone --no-local /app/repo "$work"
git -C "$work" config user.email async_rbench@example.invalid
git -C "$work" config user.name 'Async-RBench event authority'

rewrite_branch() {
  branch="$1"
  git -C "$work" switch "$branch"
  printf 'authority-v2:%s\n' "$branch" > "$work/RELEASE-AUTHORITY"
  git -C "$work" add RELEASE-AUTHORITY
  GIT_AUTHOR_DATE='2026-01-01T00:00:00Z' \
  GIT_COMMITTER_DATE='2026-01-01T00:00:00Z' \
    git -C "$work" commit -m "chore: adopt post-sanitization ${branch} header baseline"
}

rewrite_branch main
rewrite_branch dev
mkdir -p /app/events
git -C "$work" bundle create /app/events/authoritative-release.bundle main dev
git -C "$work" bundle verify /app/events/authoritative-release.bundle
printf 'secret[lost_and_found_in_git]\n' > /app/events/recovered-secret.txt
python3 - /app/repo/bottle.py <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text()
s=s.replace("    key = touni(key)\n", "    key = touni(key)\n    if any(c in key for c in ('\\n', '\\r', '\\0')):\n        raise ValueError('Header names must not contain control characters')\n", 1)
s=s.replace("    value = touni(value)\n", "    value = touni(value)\n    if any(c in value for c in ('\\n', '\\r', '\\0')):\n        raise ValueError('Header values must not contain control characters')\n", 1)
p.write_text(s)
PY
git -C /app/repo diff -- bottle.py > /app/events/bottle_crlf_fix.patch
git -C /app/repo checkout -- bottle.py
cat > /app/events/validation_test.py <<'PY'
"""Reusable regression intent for Bottle header control rejection."""
CONTROLS = ("\n", "\r", "\0")
PY
rm -rf "$work"
