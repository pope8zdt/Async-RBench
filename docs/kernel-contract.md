# Kernel contract

The kernel is evaluator-owned and frozen for official Track A. It loads the private case, builds the participant-safe episode start, controls linear/async execution, validates lifecycle events, binds child IDs to private result roles, releases real async completions, owns isolated workspaces, runs private validators/observers/checks, stores the full event source, and scores the episode.

The kernel must never send result roles, event schedules, stale or authority truth, invalidation/reopen sets, capability labels, validator commands, event-asset mappings, observer commands, hidden check IDs, hidden commands or per-check verification truth to the adapter.

Participant-visible data is constructed by allowlist and written to `participant_trace.jsonl`. Evaluator facts are separate kernel-private events. The scorer may join the two streams by opaque identifiers such as `completion_id`; the live adapter may not.

Only `linear` and `async` are valid execution modes. In async mode, completion
order is observed rather than prescribed. The complete benchmark-owned initial
wave is admitted using a separate fixed capacity of at most eight workstreams;
the participant's replacement-child limit remains three. `scenario_constructed`
is strictly an infrastructure audit. Early participant termination leaves the
episode scored and is recorded as incomplete `scenario_exposure`.

Official eligibility requires the fixed reference API harness, real API backend, isolated containers, passing conformance, public/private audits, private verifier execution and matching source/contract/manifest/verifier digests.
