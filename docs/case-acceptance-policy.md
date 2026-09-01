# Case acceptance and dataset expansion policy

This policy is the release gate for expanding Async-RBench beyond the seed cases. Its
machine-readable source is `dataset_policy.json`. The current state is
`pre_calibration_locked`: the design is fixed for the small calibration run, but the
evaluation contract remains in development until real calibration evidence passes.

## Before authoring a case

1. Assign exactly one primary event theme, one async scenario class, one dataset
   split, and a target family/instance identifier.
2. Check the current `dataset-audit` deficits. Fill a deficit rather than cloning the
   easiest existing pattern. The 450-instance target and all exact target counts are
   defined in `dataset_policy.json`.
3. Preserve source provenance. A source trajectory may justify the event design, but
   it is never participant input, Oracle truth, verifier input, or an action-sequence
   target.
4. Complete the human trajectory and technical-design reviews before scaffolding.
5. Bind a dynamic decision contract containing prior state, late event, affected
   scope, required response, forbidden response and evaluator-observable evidence.

## Admission gate

A candidate can be promoted only when all of the following are true:

- its public/private/task contracts validate and contain no private-to-public leak;
- every source instruction is either preserved verbatim before the async addendum or
  represented by an explicitly reviewed requirements manifest;
- every semantic point, dynamic-control point, workstream validator and hidden check is mapped to a concrete
  participant-visible text/file anchor in `private/quality_contract.yaml`;
- its source paths and pinned provenance validate;
- its semantic registry remains unchanged and its dynamic registry covers exactly
  `event_intake`, `state_revision`, `plan_revision`, and `closure`, with at least
  one critical point;
- its mutation design covers every registered point, with critical points covered by
  at least two mutation families;
- its dataset split and objective difficulty profile are recorded and agree with the
  deterministic rubric;
- its Oracle output passes the hidden verifier in the isolated container workflow;
- at least one non-canonical but behaviorally equivalent solution passes the exact same
  verifier bundle;
- at least two declared semantic-error mutations execute and fail their declared scoring
  points under that same verifier bundle;
- every pseudo/runtime artifact used by control-flow scoring has an executable evaluator
  observer, so agents are never scored on an impossible commit;
- a human explicitly approves promotion.

Static admission makes a case ready for calibration, not leaderboard-ready.
Calibration must separately demonstrate 100% scenario construction/exposure for
the controlled opportunity, complete critical-dynamic mutation coverage, and
non-degenerate Dynamic Control Score across the frozen multi-model pilot.

The Oracle and hidden-verifier requirement is an executed release check. A mutation
manifest is only a design specification; it must never be reported as an executed or
killed mutant. Executed mutation evidence belongs to calibration and must come from
real verifier runs.

An Oracle-only pass is insufficient. It proves that one benchmark-owned answer matches
the verifier, but it cannot detect omitted public requirements or verifier overfitting to
the Oracle's filenames, internal symbols, formatting or action strings.

## Split and leakage rules

- `calibration` is for protocol/verifier calibration and never contributes to headline
  results.
- `development` may be used to change prompts, adapters, thresholds, and implementation.
- `test` is inaccessible during those changes and is opened only after contract freeze.
- A source task or near-duplicate group must not cross splits. Near duplicates share
  the source-task set, event schedule, affected artifacts, and hidden-check semantics.

## Difficulty

Difficulty is not assigned by intuition or by the source benchmark label. The audit
computes a structural score from workstreams, milestones, dependency edges, artifacts,
async events, invalidations, reopened milestones, and instruction length. The stored
label must match the thresholds in `dataset_policy.json`. Pilot pass rates remain a
separate empirical diagnostic and may motivate later rebalancing before final freeze.

## Freeze boundary

Passing static validation means “ready for calibration,” not “frozen.” Contract freeze
requires real model point-response evidence and real executed mutation evidence to pass
`calibration-audit` with zero gaps. No placeholder rows, synthetic passes, or inferred
kill results are permitted.

`dataset-audit` deliberately reports structural validity and publication readiness as
separate fields. Legacy seed cases may remain structurally executable, but
`publication_ready` and `expansion_complete` stay false while any registered instance
lacks a passing transformed-case quality contract. This prevents an old runnable case
from silently entering the frozen paper dataset under weaker standards.

The paper-freeze job must run `python -m async_rbench.cli dataset-audit
--require-publication-ready`; the ordinary audit remains usable during expansion and
therefore exits successfully when the current partial dataset is structurally valid.
