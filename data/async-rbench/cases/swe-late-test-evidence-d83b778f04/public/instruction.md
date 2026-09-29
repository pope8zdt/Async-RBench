revert(help): Partial revert of 3c049b4

The extra whitespace was targeted at machine processing for a subset of
users for a subset of runs of CLIs.  On the other hand, there is a lot
of concern over the extra verbose output.

A user can set the help template for man, if desired.  They can even do
something (env? feature flag?) to make it only run when doing man
generation.  We also have #3174 in the works.

So let's focus on the end-user reading `--help`.  People wanting to use
`help2man` have workarounds to do what they need.

Fixes #3096

ASYNC-RBENCH EXTENSION

The source task above remains the final-state contract. The benchmark starts
2 independent workstreams whose evidence may arrive after you
have begun the implementation. Their public scopes are:
- Workstream 1: Render author and about sections with the reverted newline contract. Review together: Apply the layout consistently to short and long help.
- Workstream 2: Preserve unrelated parser and display-width behavior.

Before closing the task, persist a provisional checkpoint at
`/app/output_data/provisional_checkpoint.json` and a record of source facts
that remain valid at `/app/output_data/preserved_source_facts.json`. Consume
the delivered receipt for `clap-rs__clap-3179`, revise only state affected by that
evidence, rerun the source-native checks, and write
`/app/output_data/decision_manifest.json` with the provided manifest script.
The final state must satisfy the original task even when completion order
differs; a response without the receipt-bound closure artifacts is incomplete.
