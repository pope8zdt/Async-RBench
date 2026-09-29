fix: Fixes destructuring signal with await bug

Fixes #9686 and #9312 and #9982. Because I can't find a place to determine if an expression is asynchronous, and I can't find a builder for async/await, I ended up building it. Hopefully it's good enough, but comments and feedback and advice is most certainly welcome, because I could be wrong :)

## Svelte 5 rewrite

Please note that [the Svelte codebase is currently being rewritten for Svelte 5](https://svelte.dev/blog/runes). Changes should target Svelte 5, which lives on the default branch (`main`).

If your PR concerns Svelte 4 (including updates to [svelte.dev.docs](https://svelte.dev/docs)), please ensure the base branch is `svelte-4` and not `main`.

### Before submitting the PR, please make sure you do the following

- [x] It's really useful if your PR references an issue where it is discussed ahead of time. In many cases, features are absent for a reason. For large changes, please create an RFC: https://github.com/sveltejs/rfcs
- [x] Prefix your PR title with `feat:`, `fix:`, `chore:`, or `docs:`.
- [x] This message body should clearly illustrate what problems it solves.
- [x] Ideally, include a test that fails without this PR but passes with it.

### Tests and linting

- [x] Run the tests with `pnpm test` and lint the project with `pnpm lint`

ASYNC-RBENCH EXTENSION

The source task above remains the final-state contract. The benchmark starts
2 independent workstreams whose evidence may arrive after you
have begun the implementation. Their public scopes are:
- Workstream 1: Add an await-expression AST builder consistent with existing builders. Review together: Detect await expressions recursively without crossing nested function scopes.
- Workstream 2: Emit async thunks only when their expression requires await. Review together: Run focused compiler output tests for direct, nested, and nested-function await cases.

Before closing the task, persist a provisional checkpoint at
`/app/output_data/provisional_checkpoint.json` and a record of source facts
that remain valid at `/app/output_data/preserved_source_facts.json`. Consume
the delivered receipt for `sveltejs__svelte-9962`, revise only state affected by that
evidence, rerun the source-native checks, and write
`/app/output_data/decision_manifest.json` with the provided manifest script.
The final state must satisfy the original task even when completion order
differs; a response without the receipt-bound closure artifacts is incomplete.
