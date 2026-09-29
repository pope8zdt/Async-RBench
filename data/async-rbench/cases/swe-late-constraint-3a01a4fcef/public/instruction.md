Require a non-empty name for Blueprints
Things do not work correctly if a Blueprint is given an empty name (e.g. #4944).
It would be helpful if a `ValueError` was raised when trying to do that.

ASYNC-RBENCH EXTENSION

The source task above remains the final-state contract. The benchmark starts
4 independent workstreams whose evidence may arrive after you
have begun the implementation. Their public scopes are:
- Workstream 1: Place the falsey-name guard before the dot-name guard in Blueprint construction.
- Workstream 2: Use the repository's expected ValueError message for an empty name.
- Workstream 3: Run Blueprint constructor tests for empty, valid, and dotted names.
- Workstream 4: Add or execute a mutation check showing that changing the predicate to `name == ''` is detected.

Before closing the task, persist a provisional checkpoint at
`/app/output_data/provisional_checkpoint.json` and a record of source facts
that remain valid at `/app/output_data/preserved_source_facts.json`. Consume
the delivered receipt for `pallets__flask-5014`, revise only state affected by that
evidence, rerun the source-native checks, and write
`/app/output_data/decision_manifest.json` with the provided manifest script.
The final state must satisfy the original task even when completion order
differs; a response without the receipt-bound closure artifacts is incomplete.
