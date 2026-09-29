# Async-RBench evaluation protocol

Async-RBench measures whether a main agent can use concurrently completing subagent work, revise its plan when assumptions change, and finish in a verified state. The architecture has two execution modes and case-level capability categories; the former five-condition design is removed.

## Frozen evaluation architecture

The formal paper protocol fixes all non-model components:

1. paired Batched (`linear`) and Async (`async`) manifest episodes;
2. fixed reference API harness;
3. kernel scheduler and result gateway;
4. isolated main/child workspaces and kernel-owned event-asset staging;
5. public/private case loader and leakage audit;
6. private result validation, artifact observation and hidden verification;
7. frozen semantic and control-flow registries;
8. scorer and case-macro aggregator with reproducibility digests.

Development runs may use custom adapters or skip isolation/conformance, but
they are not comparable to the paper's reported results.

## Execution modes

- **Batched (`linear`)**: the required subagent workstreams run concurrently,
  but their results are buffered and presented together after the required
  workstreams terminate. This is the paper's paired delivery baseline.
- **Async (`async`)**: the same workstreams run with the same resource limits,
  while results are presented individually as eligible completions arrive and
  the main agent continues working. The kernel controls release boundaries but
  does not prescribe a model-generated completion order.

The benchmark-owned initial wave has separate bounded capacity (currently at
most eight workstreams), independent of the participant's replacement-child
concurrency limit. `scenario_constructed` audits only whether the harness
established the declared execution opportunity. Infrastructure failure makes an
episode unscored. If the participant ends before all designed async results are
observed, the episode remains scored: `scenario_exposure_complete` is false and
the applicable capability points fail.

## Termination and resource contract

The official v11.0.0 horizon is 100 completed main-model responses and 40
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
5,000,000-token emergency fuse exists only for runaway protection; if crossed,
no later model call starts and the episode ends as `resource_safety_abort`,
unscored and excluded from paper aggregates.

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

Each target event has an Event Response Contract (ERC) with five components:
Change (`C`), Preserve (`R`), Forbid (`F`), Verify (`V`), and event Outcome
(`O`). The process score `P` is the mean of the applicable `C/R/F/V`
components. The per-event Dynamic Replanning Score is

`DRS_i = 100 * (P_i + O_i) / 2`.

Machine-readable episode and aggregate fields store the normalized quantity
`DRS_i / 100` on `[0, 1]`; paper tables multiply it by 100. Task-success fields
use the same normalized-storage / percentage-display convention.

The Async DRS for a task run is the mean over its scored target events. A
participant-controlled termination before a required event is reached assigns
zero to that event; construction, infrastructure, and resource-safety failures
remain unscored. Batched runs do not receive DRS.

End-to-end task success `S` is determined independently by the frozen final
task checks and is reported for both Batched and Async. DRS is never blended
with task success in a paper headline. Within each repetition, the aggregate
averages the 25 tasks in a scenario; each scenario reports the mean and sample
standard deviation of its three repetition-level means. Overall DRS is the
unweighted mean of the eight scenario means. Legacy dynamic-control and DTScore
fields may appear in older machine-readable artifacts only as compatibility
diagnostics; they are not paper metrics.

For a given case and execution mode, all models share the same applicable-point
set. The denominator digest binds score-policy version, point id, measurement
type, dynamic dimension, relevance weight and criticality. Paper-comparable
episodes use the fixed harness, isolated containers, the reference API adapter,
matching digests, and the current score policy.
