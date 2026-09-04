# Async-RBench evaluation protocol

Async-RBench measures whether a main agent can use concurrently completing subagent work, revise its plan when assumptions change, and finish in a verified state. The architecture has two execution modes and case-level capability categories; the former five-condition design is removed.

## Frozen evaluation architecture

Official Track A fixes all non-model components:

1. paired `linear` and `async` manifest episodes;
2. fixed reference API harness;
3. kernel scheduler and result gateway;
4. isolated main/child workspaces and kernel-owned event-asset staging;
5. public/private case loader and leakage audit;
6. private result validation, artifact observation and hidden verification;
7. frozen semantic and control-flow registries;
8. scorer and case-macro aggregator with reproducibility digests.

Development runs may use custom adapters or skip isolation/conformance, but they are ineligible and never enter the official leaderboard.

## Execution modes

- `linear`: the same workstreams run without initial-wave overlap. It is the paired task baseline.
- `async`: the initial wave overlaps and results are released in their real completion order. The kernel does not script the order.

The benchmark-owned initial wave has separate bounded capacity (currently at
most eight workstreams), independent of the participant's replacement-child
concurrency limit. `scenario_constructed` audits only whether the harness
established the declared execution opportunity. Infrastructure failure makes an
episode unscored. If the participant ends before all designed async results are
observed, the episode remains scored: `scenario_exposure_complete` is false and
the applicable capability points fail.

## Termination and resource contract

The official v10.1 horizon is 100 completed main-model responses and 40
completed responses per child attempt. A response is one model step regardless
of how many tool calls it contains. Reaching the main horizon produces
`step_limit_reached` and remains a scored participant outcome.

`finish(status, summary)` ends the episode immediately. It is not rejected for
an unpresented delivery, open response window, missing final commit, or stale
verification. Those closure facts are recorded in `finish_quality`, while the
private final verifier independently determines task correctness. A main
response with no tool call is an implicit incomplete stop; a child response
with no tool call is `no_submission`. The framework adds no coaching retry.

Actual provider-reported tokens are recorded for main, child, each actor, and
the episode total. They do not participate in normal call admission. A shared
20,000,000-token emergency fuse exists only for runaway protection; if crossed,
no later model call starts and the episode ends as `resource_safety_abort`,
unscored and leaderboard-ineligible.

## Capability categories

Cases may target `late_revision_adoption`, `stale_result_rejection`, `inflight_cancellation`, `selective_invalidation`, `cascading_replan`, `verification_reopen`, `failure_redelegation`, and `conflict_arbitration`. These labels classify cases for analysis and are not sent to participants.

## Event themes

Capabilities describe what the agent must do; event themes describe the
evaluator-owned stimulus used to measure it. They are separate contract
dimensions. Each case has exactly one private primary event theme for dataset
counting, optional secondary themes, and one private async scenario class
(`result_eventful`, `live_eventful`, or `resource_eventful`). The frozen eight
themes are defined in `event_taxonomy.json`.

Source trajectories support discovery, workstream decomposition, source review
and provenance only. They are never participant input, oracle truth, verifier
input, or action-sequence scoring targets.

## Information boundary

The public case contains the user task, workstream instructions, public artifact contract and structural evidence schema. The private case contains result-role bindings, exact validators, event truth, stale/authority relations, invalidation/reopen anchors, hidden checks and capability labels.

Every participant-visible message is built from an allowlist. Private facts are recorded separately and joined only inside scoring. Event assets, observer commands and hidden verification commands never cross the adapter boundary.

## Scoring

Each case freezes unchanged semantic points and evaluator-observed dynamic-control
points. A task-causal Case IR compiles independent decision groups from the task
requirements, dependency closure, event policy and observable evidence. The tags
`event_intake`, `state_revision`, `plan_revision`, and `closure` locate failures in
the response lifecycle but do not receive fixed score mass. Relevance tiers weight
points inside one decision group; the number of semantic checks cannot change
dynamic score mass.

The primary async metric is Dynamic Control Score `D`, the macro mean of the
case-specific causal decision-group scores. Stage scores are diagnostics. Semantic
Task Score `S` is reported independently for both
modes. The secondary `DTScore = 0.80 D + 0.20 S`. Dynamic success additionally
requires `D >= 0.75` and every critical dynamic point to pass. Linear episodes
have no dynamic score; the paired effect is `linear S - async S`, never a
subtraction of unlike mixed denominators.

For a given case and execution mode, all models share the same applicable-point
set. The denominator digest binds score-policy version, point id, measurement
type, dynamic dimension, relevance weight and criticality. Only fixed-harness,
containerized, API-only, conformant Track A episodes with matching digests and
the current score policy are leaderboard eligible.

## Dataset expansion

After architecture freeze, a Case Factory may screen authoritative benchmark trajectories and transform selected tasks into this public/private contract. Every generated case must bind a task-causal Case IR (requirements, dependency graph, prior and revised state, affected closure, preservation boundary, required and forbidden responses, observable evidence and local negative mutations) and pass schema, leakage, information-sufficiency, event-policy, mutation-locality, protocol, scenario-construction and verifier tests. Case generation cannot alter the frozen harness.
