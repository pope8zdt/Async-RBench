# Website implementation

- `website/` uses Next.js static export. GitHub Pages publishes only `website/out/`; pull requests validate and build without deploying.
- Home and `/tasks` report the full current registry, distinguishing cases from registered instances. `scripts/catalog.py` reads classification metadata locally and exports allowlisted theme counts, without private case content.
- The main leaderboard remains the fixed 47-case cohort. `/leaderboard` switches between paired Linear/Async BTS and Async DRS, preserving search. Only complete reviewed submissions receive formal ranks; incomplete main snapshots show provisional values and coverage.
- `/evaluate` creates real Track A provider configuration and local launch scripts. The child model is optional and defaults to the main model. Advanced options support separate child provider credentials/address, token parameter naming and optional seed transmission. No fixed child-model pool is a public condition.
- Track B is simulation, including reserved framework and component interfaces. It generates no real result or submission eligibility.
- `async_rbench.submissions` packages manifest-bound aggregate results, validates them and creates separate digest-bound maintainer reviews. Entries and reviews are immutable by default. Repository review permissions govern publication; the checker does not authenticate score truth or reviewer identity.
- `scripts/refresh_results.py` previews or explicitly updates the versioned main snapshot. `scripts/prepare_data.py` validates publication inputs and builds the corpus and merged leaderboard before each site build. No server, database, automatic model execution or participant telemetry is needed.
- Execution status is unknown without telemetry. Coverage, material review and independent reproduction are displayed separately. Detail pages show per-theme metrics and measured resource means when present.

See [participant submission instructions](../../submissions/README.md) and [deployment instructions](deployment.md) for the actual commands.
