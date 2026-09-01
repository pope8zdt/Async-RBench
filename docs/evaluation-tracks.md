# Evaluation tracks

## Track A — official

Track A is the only publication/leaderboard track. It fixes the reference API harness, kernel, two-mode manifest design, container isolation, conformance suite, case contracts, private verifier, scoring and aggregation. Participants configure supported model/API settings but cannot replace orchestration code.

Eligibility is recorded per episode. Any custom adapter, scripted backend, disabled workspace, skipped conformance, contract drift or digest mismatch moves the run out of Track A instead of silently mixing it into official results.

## Development runs

Development runs exist for debugging adapters, cases and infrastructure. They may disable containers, use deterministic backends, skip conformance or use another adapter. Their scores and diagnostics are reported separately and cannot affect the official leaderboard.

Both tracks use only `linear` and `async`; old five-condition and shared-fork designs are not supported.
