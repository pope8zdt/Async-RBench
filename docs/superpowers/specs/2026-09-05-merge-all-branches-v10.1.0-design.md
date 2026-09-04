# Merge All GitHub Branches into Async-RBench v10.1.0

## Objective

Produce one authoritative GitHub branch, `main`, whose history contains every
current remote branch tip, whose shared files reflect the newest compatible
content, and whose framework version remains exactly `10.1.0`. The runnable
61-case cohort is the formal experiment and receives a dedicated directory
without duplicating the canonical case implementations under `cases/`.

## Remote Branch Snapshot

The integration covers every head returned by `git ls-remote --heads origin` on
2026-09-05:

- `main` at `eaa854c5`;
- `codex/v10.1-step-bounded-termination` at `eaa854c5`;
- `codex/paper-eval-80-redesign` at `9812e319`;
- `codex/paper-eval-existing-61` at `9812e319`;
- `codex/paper-eval-existing-61-v10.1.0` at `3e604972` (discovered by
  the mandatory execution-time refresh);
- `feat/mab-authority-infra-unscored` at `1a353d46`.

Before pushing or deleting branches, the remote heads must be fetched again.
If a head has moved or a new head exists, it must be incorporated and verified
under the same rules before cleanup continues.

## History and File Precedence

Integration starts from `origin/main`, the v10.1.0 release baseline. Merge
commits must make each distinct remote branch tip an ancestor of the final
commit; branches that share a tip or already equal `main` require no duplicate
content merge.

For paths changed on more than one branch, the later intended state supersedes
the older state. Commit timestamps establish recency, but a later feature
branch may not undo the explicitly required v10.1.0 framework contract. The
newest v10.1-compatible 61-case state is the local commit `3e604972`, created by
replaying the 61-case feature onto `eaa854c5`; its versions of the seven
61-case feature paths are the conflict-resolution reference. Unique files from
older branches remain present unless superseded by a later rename or deletion.

The final tree therefore combines:

- all v10.1.0 runtime and contract changes from `origin/main`;
- the 61-case selection, launcher support, validation code, tests, and design
  history from the two remote paper-evaluation branch names;
- the unique project-structure design document from
  `feat/mab-authority-infra-unscored`;
- the dedicated formal-experiment directory described below.

## Formal 61-Case Experiment Layout

Experiment-owned entry files move to:

```text
experiments/formal-61/
|-- README.md
|-- paper-eval-existing-61.csv
`-- run.ps1
```

`paper-eval-existing-61.csv` contains exactly 61 ordered rows and is the frozen
experiment cohort. `run.ps1` is the supported launcher. The directory README
documents the cohort, prerequisites, validation-only command, execution
command, expected outputs, and the fact that the case implementations remain
canonical under top-level `cases/`.

Library code remains at `async_rbench/paper_eval.py` and its automated tests
remain under `tests/`; these are framework code, not duplicated experiment
assets. All defaults, launch commands, tests, and documentation must reference
the new experiment paths. The former root launcher and former cohort CSV path
must not remain as duplicate active entry points.

## Root README and Version Contract

The root `README.md` must identify the framework as Async-RBench v10.1.0 and
link to `experiments/formal-61/README.md` as the formal experiment. Its example
commands must use `experiments/formal-61/run.ps1` and the new cohort path.

The active version declarations must remain consistent:

- `pyproject.toml`: `10.1.0`;
- `async_rbench/__init__.py`: `10.1.0`;
- `async_rbench/evaluation/version.py`: `10.1.0`;
- `evaluation_contract.json`: `10.1.0`;
- root README badge and version section: `10.1.0`.

The existing `v10.1.0` tag is preserved; it is not force-moved.

## Verification

Before changing GitHub branches, the integration worktree must pass:

1. repository status and conflict-marker checks;
2. a version-consistency scan over every active declaration;
3. the 61-row cohort test and validation command;
4. manifest generation for all 61 cases in both Linear and Async modes;
5. the focused paper-evaluation and v10.1 runtime tests;
6. the repository test suite, with any pre-existing slow test reported
   separately from integration regressions;
7. an ancestry assertion that every snapshotted remote tip is reachable from
   the final integration commit.

No real model experiment is launched as part of repository integration.

## GitHub Finalization

After verification, push the integration commit to `origin/main` without a
force push. Re-fetch and prove that every non-main remote head is an ancestor
of the pushed `origin/main`. Delete these remote branch names:

- `codex/v10.1-step-bounded-termination`;
- `codex/paper-eval-80-redesign`;
- `codex/paper-eval-existing-61`;
- `codex/paper-eval-existing-61-v10.1.0`;
- `feat/mab-authority-infra-unscored`.

Finally, `git ls-remote --heads origin` must return only `refs/heads/main`.
Local branches and existing worktrees are not deleted because the requested
cleanup is specifically for GitHub, and some contain uncommitted user work.

## Safety and Recovery

The dirty primary checkout is never reset, cleaned, stashed, or used for the
merge. All integration work occurs in the isolated
`codex/merge-all-to-main-v101` worktree. Remote branches are deleted only after
their tips are reachable from `origin/main`, so their commits remain
recoverable through `main` history.
