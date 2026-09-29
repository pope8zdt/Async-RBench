#!/usr/bin/env bash
# Deterministic fixture builder for git-conflict-and-cleanup-closure.
#
# Derives from the upstream Terminal-Bench git-leak-recovery challenge setup:
#   upstream/terminal-bench/original-tasks-locked/git-leak-recovery/challenge-setup.sh
# (init repo, commit a secret, then `git reset --hard HEAD~1` to leave the leak
# as an UNREACHABLE object that is kept alive only by the HEAD reflog). Extended
# here with a second unrelated commit and fixed commit dates so that git object
# hashes are byte-deterministic across container builds.
#
# The git reachability semantics this relies on are pinned and documented:
#   - `git fsck --lost-found` reports the reset-away commit as DANGLING even
#     though the HEAD reflog still references it (fsck reachability ignores
#     reflogs).
#   - `git gc --prune=now --aggressive` WITHOUT expiring reflogs keeps the
#     dangling commit alive (gc/prune DO treat reflogs as roots). A naive
#     cleanup therefore leaves the secret packed and recoverable.
#   - `git reflog expire --expire=now --all` followed by `git gc --prune=now
#     --aggressive` removes it completely.
set -euo pipefail

export GIT_AUTHOR_NAME="TerminalBench"
export GIT_AUTHOR_EMAIL="tb@example.com"
export GIT_COMMITTER_NAME="TerminalBench"
export GIT_COMMITTER_EMAIL="tb@example.com"
export GIT_AUTHOR_DATE="2024-01-01T00:00:00Z"
export GIT_COMMITTER_DATE="2024-01-01T00:00:00Z"

mkdir -p /app/repo
cd /app/repo
git init -q
git config user.name "TerminalBench"
git config user.email "tb@example.com"
# Reflog-reachability protection must survive any gc that runs between build and
# the participant's cleanup. The reflog entries carry the fixed commit dates
# (2024-01-01), so without this a build-time `git gc --auto` would expire them as
# >90 days old and prune the reset-away leak before the case is even served.
# Pinning `gc.reflogExpire never` makes the HEAD reflog a permanent root: a naive
# `git gc --prune=now` keeps the dangling commit (the designed trap), while an
# explicit `git reflog expire --expire=now --all` still overrides it.
git config gc.auto 0
git config gc.reflogExpire never
git config gc.reflogExpireUnreachable never

# Good commit 1: project scaffold (unrelated content that must be preserved).
cat > README.md <<'EOF'
demo project

maintains apartment-scraping notes.
EOF
mkdir -p docs src tools
cat > docs/roadmap.md <<'EOF'
# Roadmap
- Q1: inventory scripts
- Q2: lease workflow
EOF
cat > src/main.py <<'EOF'
def main():
    print("scratch project")
EOF
git add .
git commit -q -m "chore: init scaffold"

# Leak commit: a secret is committed to the repo.
echo "secret[stockholm_linnea_0815]" > secret.txt
git add secret.txt
git commit -q -m "feat: add scratch notes"

# History is rewritten away from the leak. The leak commit is now unreachable
# from any ref, but the HEAD reflog keeps it alive (see header note).
git reset --hard -q HEAD~1

# Good commit 2: an unrelated follow-up on top of the now-clean history.
cat > tools/cleanup_check.sh <<'EOF'
#!/bin/bash
echo "ok"
EOF
git add .
git commit -q -m "feat: add tools script"

# The repo is left with exactly two reachable commits:
#   "feat: add tools script"  (HEAD)
#   "chore: init scaffold"
# and one dangling commit: "feat: add scratch notes" (holds the secret).
