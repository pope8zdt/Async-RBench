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
  python3 - "$work/bottle.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()
start = source.index("def _hkey(key):")
end = source.index("class HeaderProperty:", start)
baseline = '''def _header_text(value):
    """Post-sanitization release baseline normalization helper."""
    return touni(value)


def _hkey(key):
    key = _header_text(key)
    return key.title().replace('_', '-')


def _hval(value):
    value = _header_text(value)
    return value


'''
path.write_text(source[:start] + baseline + source[end:])
PY
  git -C "$work" add bottle.py
  GIT_AUTHOR_DATE='2026-01-01T00:00:00Z' \
  GIT_COMMITTER_DATE='2026-01-01T00:00:00Z' \
    git -C "$work" commit -m "chore: adopt post-sanitization ${branch} header baseline"
}

rewrite_branch main
rewrite_branch dev
mkdir -p /app/events
git -C "$work" bundle create /app/events/authoritative-release.bundle main dev
git -C "$work" bundle verify /app/events/authoritative-release.bundle
rm -rf "$work"
