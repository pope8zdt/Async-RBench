# Participant workflow and benchmark presentation

User requirements: experiment conditions do not include a fixed child model pool; task descriptions always report the current repository case total and show its theme distribution; leaderboard switches between paired Linear/Async BTS and Async DRS. Continue the previously proposed participant-local submission, validation, review and static publication workflow. Track B remains explicitly simulated.

- Compute case totals from the current registered repository cases, distinguishing 200 cases from 201 registered instances when that is the current data. Do not hardcode either number. The main leaderboard remains exactly the immutable 47-case cohort.
- The website does not demand or display a fixed child-pool identity as an experimental factor. A child model may remain a runtime configuration choice. Preserve frozen per-episode scoring and existing manifests.
- Public records distinguish incomplete/complete coverage, unknown execution status unless explicitly reported, and self-reported/materials-reviewed/independently-reproduced provenance. Never infer a running process from missing scores.
- Publish only allowlisted aggregate records, configuration hashes and safe reproducibility metadata. Raw scores, private traces, credentials and local paths remain local.
- Provide a deterministic JSON submission envelope with content digest, strict validation, local packaging from a declared main47 manifest, and separate maintainer review records bound to that digest. Local structural validation is not independent score attestation.
- Site build merges accepted submissions into the existing main experiment snapshot, supports several distinct runs of the same model, never automatically upgrades trust, and validates cohort membership/digest before publication.
- GitHub Pages remains the public host. CI validates submissions and review records and rebuilds the site; no server or model-execution backend is required.
- Add practical participant and maintainer instructions, model-independent conditions, snapshot timestamps, local refresh command, public task overview and theme comparisons. Keep the restrained academic visual style.
