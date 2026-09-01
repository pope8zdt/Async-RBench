# PROVENANCE.md — git-conflict-and-cleanup-closure

## Source

| field | value |
|---|---|
| benchmark | terminal-bench |
| task | git-leak-recovery |
| lock commit | `d28711d0da2675d0bb1d56de45ae5df6082438a3` |
| task tree sha256 (SOURCE_LOCK.json) | `049d9e6fa8e9b79e2394d432080c07404a57e05af37f913e9f0f5f78c6971516` |
| upstream path | `upstream/terminal-bench/original-tasks-locked/git-leak-recovery` |
| trajectory origin | official Terminal-Bench task fixture (challenge-setup.sh), re-derived structurally; no third-party or non-official material labelled as official |

The upstream task directory is untouched and its lock hash is verified by
`async_rbench/provenance.py`.

## Implementation kind

`structure-derived`. The upstream `git-leak-recovery` challenge already encodes
the core trap — a secret committed and then `git reset --hard HEAD~1`-ed away,
leaving the leak as an unreachable object kept alive only by the HEAD reflog.
The derived case splits that single cleanup into concurrent workstreams
(ref/history scan, pack/tree scan, object-database scan, recovery, cleanup,
closure verification) so the async-replanning scenario falls out of the
structure: only the object-database scan reaches the leak, negative scans are
not absence, and a cleanup that ignores the reflog cannot pass closure
verification and must be redelegated.

## Byte-identical upstream material (validated by asset_copies / preserved-solution checks)

| upstream file | case file |
|---|---|
| `solution.sh` | `task/upstream_solutions/git-leak-recovery.sh` |

`asset_copies` is empty by design: the upstream `challenge-setup.sh` is not
copied verbatim. The derived fixture `task/task_file/setup_repo.sh` is a
documented transformation of it (same init → leak → reset structure) that
additionally pins fixed commit dates and the gc/reflog config so the trap is
deterministic and survives any build-time `git gc --auto`.

## Derived material (documented transformation)

- `task/task_file/setup_repo.sh`: deterministic fixture builder derived from the
  upstream `challenge-setup.sh` (init scaffold → commit secret → reset → tools
  commit). Adds `gc.auto 0`, `gc.reflogExpire never`,
  `gc.reflogExpireUnreachable never` so the reset-away commit survives a
  build-time `git gc --auto` (fixed dates would otherwise expire the reflog as
  >90 days old and prune the leak before it is served). Pinned git reachability
  semantics are documented in the script header.
- `task/task_file/scripts/scan_refs.py`, `scan_packs.py`, `scan_objects.py`:
  three public scanners. Only `scan_objects.py` (`git fsck --lost-found` plus a
  walk of every dangling commit/tree blob) reaches the rewritten-away leak; the
  other two cover reachable history and reachable packs/working tree and
  correctly report `found=false`.
- `task/task_file/scripts/recover_secret.py`: recovery must be anchored on the
  object-database authority; fails loudly otherwise.
- `task/task_file/scripts/record_cleanup.py`, `verify_closure.py`,
  `write_manifest.py`: cleanup attempt recording, repo-wide closure verification
  (reachable history / unreachable objects / full object store / working tree)
  with stamping of cleanup reports, and the decision manifest.
- `task/oracle.sh`: benchmark-maintenance reference trajectory (never shipped to
  the participant image). Runs the naive cleanup first (expects `closed=false`),
  then the complete cleanup (`git reflog expire --expire=now --all` + gc),
  records both attempts and writes the manifest.
- `task/tests/test_case_outcomes.py`, `semantic_checks.json`,
  `control_flow_checks.json`: case-specific Async-RBench outcome contract (24
  semantic checks + 4 control-flow checks), not the upstream `tests/`.

## Hidden-from-participant material

`task/tests/`, `task/run-tests.sh`, `task/oracle.sh`,
`task/upstream_solutions/` are never baked into the participant image
(`task/.dockerignore` + explicit `COPY task_file`). They are injected only into
isolated benchmark-maintenance / verifier clones. The naive-gc trap and the
reflog-expire requirement are documented in the public scripts' comments but the
recovered secret value, the authority object id and the correct cleanup strategy
are never written into any participant-visible instruction.

## Outcome contract

- 24 semantic checks (version 3): base (4), authority integration (3),
  selective replanning (5), consistency closure (12). Base weight share
  = 4 base points / (4·1 + 3·2 + 5·3 + 12·4) = 4/73 ≈ 5.5% ≤ 20%.
- 4 async-only control-flow checks cover waiting for sufficient recovery
  evidence, rejecting obsolete negative scans, cancelling superseded work and
  rebuilding cleanup evidence from the accepted result set.
- The case is classified as `conflict_arbitration`, `failure_redelegation` and
  `verification_reopen`. Linear and async modes use one frozen outcome contract.
