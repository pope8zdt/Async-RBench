# PROVENANCE.md — scheduler-selective-replan

## Source

| field | value |
|---|---|
| benchmark | terminal-bench |
| task | llm-inference-batching-scheduler |
| lock commit | `d28711d0da2675d0bb1d56de45ae5df6082438a3` |
| task tree sha256 (SOURCE_LOCK.json) | `c69dc58c86751c9bb25cf1003243dbf1ae260679d3bdfb5a6682f3ab7addc482` |
| upstream path | `upstream/terminal-bench/original-tasks-locked/llm-inference-batching-scheduler` |
| trajectory origin | official Tracebench trajectory `terminus2-DeepSeek__DeepSeek-V3.2-llm-inference-batching-scheduler-f9069cf0` (annotation only; no trajectory bytes copied into the case) |

The upstream task directory is untouched and its lock hash is verified by
`async_rbench/provenance.py`. No third-party Gaia2 trace or any other non-official
material is labelled as official here.

## Implementation kind

`structure-derived`. The case reuses the real upstream task's file layout,
public cost model, baseline packer and solution script, and derives the
async-replanning scenario from the structure the upstream task already implies
(two request buckets, one shared shape budget, one shared validator).

## Byte-identical upstream material (validated by asset_copies / preserved-solution checks)

| upstream file | case file |
|---|---|
| `task_file/scripts/cost_model.py` | `task/task_file/scripts/cost_model.py` |
| `task_file/scripts/baseline_packer.py` | `task/task_file/scripts/baseline_packer.py` |
| `task_file/scripts/__init__.py` | `task/task_file/scripts/__init__.py` |
| `solution.sh` | `task/upstream_solutions/llm-inference-batching-scheduler.sh` |

## Derived material (documented transformation)

- `task/task_file/input_data/requests_bucket_1.jsonl` / `requests_bucket_2.jsonl`:
  deterministic engineered fixtures (seed 7). Bucket 1 holds 24 requests with
  prompt lengths 64/128/192/256; bucket 2 holds 24 requests with prompt lengths
  512/768/1024. They are generated from the upstream `cost_model.py` so that a
  per-length packing passes every threshold with 7 distinct shapes (≤ the shared
  8-shape budget), while a coarse one-size packing either under-covers bucket 2
  (seq_align too small) or over-pads bucket 1 (pad_ratio above threshold).
  These replace the upstream input files; the hash-locked upstream files remain
  untouched in `upstream/`.
- `task/task_file/scripts/validate_plan.py`: new public validator shared by
  participant and verifier. Thresholds (`THRESHOLDS`) are derived from the
  reference packer's achieved metrics with a safety margin; a plan that pads
  every request into one oversized shape fails them.
- `task/upstream_solutions/reference_packer.py`: benchmark-maintenance oracle
  material (never shipped to the participant image). Produces the correct
  combined plan, the first-pass preservation snapshots, the committed global
  shape set and the decision manifest. The preserved bucket is bucket 1 (its
  first-pass plan is byte-identical to the final); the replanned bucket is
  bucket 2 (its first-pass snapshot is an under-covered coarse plan, superseded
  by the final per-length plan).
- `task/tests/test_case_outcomes.py`, `semantic_checks.json`,
  `control_flow_checks.json`: case-specific Async-RBench outcome contract (24
  semantic checks + 4 control-flow checks), not the upstream `tests/test_outputs.py`.

## Hidden-from-participant material

`task/tests/`, `task/run-tests.sh`, `task/oracle.sh`,
`task/upstream_solutions/` are never baked into the participant image
(`task/.dockerignore` + explicit `COPY task_file`). They are injected only into
isolated benchmark-maintenance / verifier clones. `reference_packer.py` encodes
which bucket is preserved and which is replanned; neither appears in
`task/task.yaml` or any public task material.

## Outcome contract

- 24 semantic checks (version 3): base (4), preservation (4), replan (4),
  global constraint (6), consistency closure (6). Base weight share
  = 4 base points / (4·1 + 4·3 + 16·4 + 4 control-weight-12) = 4/92 ≈ 4.3% ≤ 20%.
- 4 async-only control-flow checks cover waiting for both validators, rejecting
  obsolete plans, cancelling only the failing branch and recomputing the
  combined schedule from accepted results.
- The case is classified as `selective_invalidation`, `conflict_arbitration`
  and `cascading_replan`. The oracle output is identical in linear and async
  execution; the async episode changes the replanning pressure, not correctness.
