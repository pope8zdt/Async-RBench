# PROVENANCE.md — swe-bench-selective-patch

## Source

| field | value |
|---|---|
| benchmark | swe-bench |
| primary instance | `scikit-learn__scikit-learn-25638` |
| lock commit (SOURCE_LOCK.json) | `1faa91cade0562ba62b66c1c99e71f7b72d96f13` |
| instance sha256 (SOURCE_LOCK.json) | `5deca928e57a86c4377e6756f3f3690809283e316ca2a8e03617f1838c78a0d3` |
| upstream path | `upstream/swe-bench` |
| trajectory origin | SWE-bench instance scikit-learn__scikit-learn-25638, re-derived structurally; no upstream patch text is reproduced verbatim |

The upstream source is hash-locked and verified by `async_rbench/provenance.py`
against `SOURCE_LOCK.json`.

## Implementation kind

`structure-derived`. The upstream instance repairs scikit-learn's
`sklearn/utils/multiclass.py` so that pandas nullable-dtype targets are
accepted during target-type inference and label extraction (gh-25634/gh-25635/
gh-25637). There are no local gold patch files for this instance, so the case
ships a small, self-contained, deterministic trimmed sklearn package under
`task/task_file/src/sklearn` that reproduces the bug structurally: an
object-dtype (nullable) label array is misclassified by `type_of_target` as
`"unknown"` (the engine of the upstream bug), and `_unique_multiclass` cannot
take the unique set of an object-dtype array that contains a missing marker.
The derived case splits the SWE-bench verification into three independent test
module groups (metrics / preprocessing / utils) plus a smoke regression, so the
async-replanning scenario falls out of the structure: one group exercises the
nullable code path and fails until the fix is complete, while the other two
groups keep passing, and the repair must stay confined to the single fix
target file.

## Byte-identical upstream material

None. SWE-bench instances are not validated for byte-identical
preserved-solution material (that check applies to terminal-bench only), and
`asset_copies` is empty by design. The gold-fix semantics are re-derived and
recorded only in the benchmark-maintenance reference solution
(`task/upstream_solutions/reference_solution.sh`), which is never shipped to
the participant image.

## Derived material (documented transformation)

- `task/task_file/src/sklearn`: trimmed, deterministic, NumPy-only
  reproduction of the scikit-learn surfaces the fix touches. `utils/multiclass.py`
  is the faithful base (`type_of_target`, `unique_labels`, `_unique_multiclass`,
  `is_multilabel`, `check_classification_targets`) with the upstream bug
  present and un-fixed, plus a documented NumPy-2 compatibility shim for
  `np.VisibleDeprecationWarning` (base fixture only, not part of the fix).
  `metrics/_classification.py` (group A), `preprocessing/_label.py` (group B)
  and the small validation/config/base helpers reproduce the corresponding
  scikit-learn code paths structurally. `utils/validation._is_numpy_nan` treats
  `None` as the package's missing-label *marker* (not NaN), so object-dtype
  label arrays are the deterministic stand-in for pandas nullable columns
  without a pandas dependency.
- `task/task_file/tests/test_classification.py`, `test_label.py`,
  `test_multiclass.py`, `test_smoke.py`: the three module-group test runners
  plus the smoke regression. Group B's `LabelBinarizer` tests exercise the
  nullable path (fit, transform, inverse round-trip with a `None` marker);
  groups A and C exercise the plain label path.
- `task/task_file/scripts/run_module_group_{a,b,c}.py`, `run_regression.py`,
  `record_fix.py`, `record_integrated.py`, `write_manifest.py`: public runner
  and recording scripts. Each report carries the fix-target revision it ran
  against so a result produced against a superseded revision is detectable.
- `task/task_file/setup_package.sh`: build-time fixture builder that records
  the base (buggy) revision of every source file into
  `task/task_file/src/BASE_MANIFEST.json` and is then removed from the image.
- `task/oracle.sh`: benchmark-maintenance reference trajectory (never shipped
  to the participant image). Applies an *incomplete* first fix (object-to-float
  conversion without missing-marker handling) that passes groups A and C but
  leaves group B failing, archives the failure, then runs the reference
  solution (complete fix) and re-verifies every group plus the regression
  before assembling the manifest.
- `task/upstream_solutions/reference_solution.sh`: the complete gold-fix
  semantics (two hunks in `sklearn/utils/multiclass.py`: missing-marker-safe
  `type_of_target` conversion and `_unique_multiclass`). Structure-derived from
  the upstream instance; no upstream patch text.
- `task/tests/test_case_outcomes.py`, `semantic_checks.json`,
  `control_flow_checks.json`: case-specific Async-RBench outcome contract (24
  semantic checks + 4 control-flow checks), not the upstream SWE-bench test
  files (the upstream test suite is not replayed).

## Hidden-from-participant material

`task/tests/`, `task/run-tests.sh`, `task/oracle.sh`,
`task/upstream_solutions/` are never baked into the participant image
(`task/.dockerignore` + explicit `COPY task_file`); they are injected only into
isolated benchmark-maintenance / verifier clones. The participant-facing
instructions never reveal which module group fails, the order in which results
arrive, the gold patch, or the expected pass/fail per group, and the image
never contains the reference solution or any patch/diff artifact.

## Outcome contract

- 24 semantic checks (version 3): base (4), async_result_integration (6),
  async_dynamic_replanning (6), async_consistency_closure (8). Base weight
  share = 4 base points / (4·1 + 6·2 + 6·3 + 8·4) = 4/66 ≈ 6.1% ≤ 20%.
- 4 async-only control-flow checks cover waiting for required evidence,
  rejecting an obsolete completion, cancelling superseded work and deriving
  the final repair from accepted evidence.
- The case is classified as `stale_result_rejection`,
  `selective_invalidation` and `verification_reopen`. Linear and async modes
  share the same task outcome contract; only completion timing and the needed
  replanning behavior differ.
