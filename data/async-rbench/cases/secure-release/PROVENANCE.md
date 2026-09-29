# Registered-case provenance

- **Release:** `v11.0-paper`
- **Case ID:** `secure-release`
- **Title:** Sanitize, patch, and deploy a revisioned release

## Source identity

- **Terminal-Bench** task `git-leak-recovery`; source snapshot `upstream/terminal-bench/original-tasks-locked/git-leak-recovery`
- **Terminal-Bench** task `fix-code-vulnerability`; source snapshot `upstream/terminal-bench/original-tasks-locked/fix-code-vulnerability`
- **Terminal-Bench** task `git-multibranch`; source snapshot `upstream/terminal-bench/original-tasks-locked/git-multibranch`
- **Terminal-Bench** task `nginx-request-logging`; source snapshot `upstream/terminal-bench/original-tasks-locked/nginx-request-logging`

## Transformation and review

This registered Async-RBench case preserves the source task objective and the
participant-visible executable materials needed to solve it. The benchmark
adds a bounded multi-workstream execution contract; controlled result delivery
and scoring are supplied only by the separately versioned judge bundle.

The frozen public case was manually reviewed for source identity,
participant-input sufficiency, executable task setup, and consistency between
the public instruction and artifact contract.

## Publication boundary

This record contains no event schedule, evaluator-only release condition,
event-response contract truth, verifier, oracle, reference solution, invalid
mutation, hidden test, or canonical answer. Those materials are excluded from
the public repository and are bound to the release through external digests.
