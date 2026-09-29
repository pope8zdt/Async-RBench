# Git Leak Recovery Closure (structure-derived)

The executable participant instruction is [task/task.yaml](task/task.yaml). This
case is derived from the Terminal-Bench task `git-leak-recovery` (lock commit
`d28711d0da2675d0bb1d56de45ae5df6082438a3`): a secret is committed, removed by
rewriting history, and must be recovered and cleaned repo-wide while unrelated
files and history stay untouched. The upstream fixture's reset-away-dangling-
commit structure is reused with fixed commit dates and a second unrelated
commit, so three independent scans (ref/history, pack/working-tree, object
database) return different results and only the object-database scan reaches
the rewritten-away secret. A naive `git gc --prune=now` genuinely leaves the
dangling commit packed (the reflog keeps it alive), so the closure verifier
fails and the cleanup must be re-delegated with reflog expiry and re-verified
before completion. Private scoring checks authority-based recovery, repo-wide
closure, preservation of unrelated history, and the recorded rejection /
redelegation process. The upstream task suite is not replayed.
