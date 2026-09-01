Force sorting with `next_display_order(None)`

This also extends to subcommands.

Previous behavior:
- They'd be sorted by default
- They'd derive display order if `DeriveDisplayOrder` was set
  - This could be set recursively
- The initial display order value for subcommands was 0

New behavior:
- Sorted order is derived by default
- Sorting is turned on by `cmd.next_display_order(None)`
  - This is not recursive, it must be set on each level
- The display order incrementing is mixed with arguments
  - This does make it slightly more difficult to predict

And with that, we can remove `AppSettings` from the API, helping towards #3021

Fixes #2808

ASYNC-RBENCH EXTENSION

The source task above remains the final-state contract. The benchmark starts
2 independent workstreams whose evidence may arrive after you
have begun the implementation. Their public scopes are:
- Workstream 1: Implement non-recursive per-command sorting activation. Review together: Mix argument and subcommand display-order increments as specified.
- Workstream 2: Update all inventoried consumers and remove obsolete AppSettings exposure. Review together: Run nested-command ordering and API tests.

Before closing the task, persist a provisional checkpoint at
`/app/output_data/provisional_checkpoint.json` and a record of source facts
that remain valid at `/app/output_data/preserved_source_facts.json`. Consume
the delivered receipt for `clap-rs__clap-3975`, revise only state affected by that
evidence, rerun the source-native checks, and write
`/app/output_data/decision_manifest.json` with the provided manifest script.
The final state must satisfy the original task even when completion order
differs; a response without the receipt-bound closure artifacts is incomplete.
