# Contributing

Thank you for improving Async-RBench.

## Before opening a change

1. Install the project with `python -m pip install -e ".[test]"`.
2. Run `python -m async_rbench.cli validate-public`.
3. Run the relevant tests under `tests/`.
4. Do not add judge material, credentials, run outputs, or upstream repository
   checkouts to the public tree.

## Case changes

A registered case must keep participant-visible content under `public/` and
`task/`. Hidden tests, solutions, event policy, oracle data, mutations, and
verifier code belong in an external judge root. Source changes must record a
stable task ID, revision, and content commitments; changing only a benchmark
label or case name is not a source rebinding.

Any accepted corpus change must regenerate the public and judge release
manifests together and preserve the paper release invariants documented in
`docs/dataset.md`.

## Pull requests

Keep changes reviewable, explain any corpus-count effect, and include the exact
validation commands and results. Never include private judge files in a patch.

