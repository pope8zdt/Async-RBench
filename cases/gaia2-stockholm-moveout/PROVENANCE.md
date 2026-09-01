# PROVENANCE.md — gaia2-stockholm-moveout

## Source

| field | value |
|---|---|
| benchmark | gaia2 |
| scenario | `scenario_universe_21_xvc7uo` (validation split, category time) |
| lock commit | `78ea3bdbdeec2bdcd6afa542091` |
| scenario sha256 (SOURCE_LOCK.json) | `614f90b7f13ed6952e1d210cf47929a389c005be8c47d42708049cf59c101a46` |
| source URL | `https://huggingface.co/datasets/meta-agents-research-environments/gaia2` |
| license / access | cc-by-4.0, not gated |
| trajectory origin | structure_derived_from_official_scenario (official events + oracle action DAG); no trajectory bytes are copied into the case |

The upstream GAIA2 source tree is untouched and the hash lock in
`upstream/gaia2/SOURCE_LOCK.json` is verified by `async_rbench/provenance.py`. No
non-official material is labelled as official here.

## Implementation kind

`structure-derived`. The case re-implements the official scenario's semantics
(Stockholm saved-list maintenance + late listing notifications) with local
editorial assets: simulated RentAFlat/Contacts apps, a deterministic listing
feed, and an oracle that derives the same answer from those public files. It is
an agentic re-implementation of the scenario's task, not a re-run of the
official environment or its suite.

## Byte-identical upstream material

None. `asset_copies` is empty because the GAIA2 source ships the scenario only
inside a parquet dataset (plus `SOURCE_LOCK.json`); there is no per-scenario
file that could be copied byte-identically into a case container. The scenario
semantics are reproduced editorially and cross-checked against the official
prose definition recorded in the design spec.

## Derived material (documented transformation)

- `task/task_file/app/raf_saved_list.json`, `raf_catalog.json`,
  `contacts.json`: deterministic engineered fixture of the RentAFlat apps. The
  saved list deliberately contains one out-of-range Stockholm listing to remove,
  one non-Stockholm saved listing that must survive untouched, and one unsaved
  in-range Stockholm catalog listing to add.
- `task/task_file/event_feed/feed.jsonl` + `feed_meta.json`: the deterministic
  replacement for the environment's listing stream. Six pre-registered events at
  simulated arrival times 32/60/72/113/132/140 (matching the official ENV event
  timeline): two in-range Stockholm listings and four decoys (over-budget
  Stockholm, far-over-budget Stockholm, under-budget Stockholm, out-of-city
  Göteborg). The window is 4 simulated minutes, as in the official scenario.
- `task/task_file/scripts/`: `read_events.py` (stateless feed reader with
  `--tick`/`--since`), `send_message.py` (Messages outbox writer),
  `write_manifest.py` (manifest merger), plus read-only app readers.
- `task/upstream_solutions/reference_solution.py`: benchmark-maintenance oracle
  material (never shipped to the participant image). It reads the public apps
  and feed directly and deterministically writes the correct
  `planned_ops.json`, `saved_list_final.json`, `notifications.jsonl`,
  `event_monitor_report.json` and `decision_manifest.json`.

## Documented derivation: the 1800 SEK budget

The official scenario expresses Linnea's budget only in prose as the 1000–1800
SEK range. The local case therefore records a numeric budget: `budget_sek: 1800`
in `contacts.json`, derived from the scenario's 1000–1800 range bound, and
asserted equal to `search_preferences.max_rent_sek` by the oracle. This is a
documented local derivation, **not** an official Gaia2 field, and must not be
presented as one.

## Async design and mode invariance

The case uses the same apps, feed, scripts and correct final state in both
execution modes. Linear execution provides the baseline. Async execution lets
the independently running workstreams complete in their actual order, creating
late-revision adoption, selective invalidation and verification-reopen pressure
without revealing evaluator role or staleness labels to the participant. The
oracle therefore produces one deterministic reference output for both modes.

## Hidden-from-participant material

`task/tests/`, `task/run-tests.sh`, `task/oracle.sh`,
`task/upstream_solutions/` are never baked into the participant image
(`task/.dockerignore` + explicit `COPY task_file`); they are injected only into
isolated benchmark-maintenance / verifier clones. The reference solution encodes
which listings match and that exactly two notifications are owed; neither the
matching listings, their prices, the two-message expectation nor the event
ordering appear in `task/task.yaml` or any public task material. The notification
predicate is derivable only by reading the simulated apps.

## Outcome contract

- 24 semantic checks (version 3): base (4), late-listing integration (4),
  selective notification (6), event evaluation (4), consistency closure (6).
  Weighted by relevance tier (base 1, supporting 2, direct 3, critical 4):
  base 4·1 = 4, integrate 4·3 = 12, notify 4·4 + 2·3 = 22, eval 2·2 + 2·3 = 10,
  closure 6·4 = 24 → semantic total 72; base weight share = 4/72 ≈ 5.6% ≤ 20%.
  The four control gates (weight 12 each) are scored separately.
- 4 async-only control-flow checks cover waiting for closure evidence, rejecting
  obsolete inputs, cancelling superseded planning and rebuilding the saved-list
  artifact from accepted revisions.
- The upstream GAIA2 suite is not replayed; the case carries its own frozen
  `test_case_outcomes.py` as the leaderboard contract.
