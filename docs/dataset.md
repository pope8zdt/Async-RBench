# Dataset

Async-RBench contains 200 registered cases, each with one registered instance.
A case is the registration unit; an instance is one executable variant of it.

## Event themes

Every case belongs to exactly one of eight primary event themes. The themes are
the benchmark's eight case families, and they are the unit of the headline
macro average.

| Theme | Definition |
|---|---|
| `delayed_authoritative_result` | An independently produced authoritative result becomes available after provisional downstream work has begun. |
| `late_or_out_of_order_superseded_result` | A superseded result arrives late or out of order after a newer authority is available. |
| `partial_then_complete_result` | A useful partial result is followed by a more complete result that changes required integration work. |
| `conflicting_valid_results` | Two independently valid-looking results conflict and require arbitration rather than blind aggregation. |
| `duplicate_or_replayed_completion` | The gateway replays an already delivered completion without creating a second child completion. |
| `child_failure_or_implicit_error` | A child times out, crashes, or returns a structurally valid payload whose evidence represents an implicit failure. |
| `task_scope_or_dependency_change` | New evaluator-owned information changes the task scope or dependency graph while work is in flight. |
| `straggler_under_resource_pressure` | A straggler remains in flight while concurrency, token, or deadline pressure constrains the main agent's choices. |

Counting rule: each case is counted exactly once, by `primary_event_theme`.
Capabilities are independent multi-label measurements and are never added to
event-theme counts.

## Paper release composition

`v11.0-paper` freezes 200 cases and 621 initial subtasks. Each source contributes
40 cases: GAIA2, MultiAgentBench, OSWorld, SWE-bench, and Terminal-Bench. The
difficulty split is 104 medium and 96 hard. The initial-subtask histogram is 73
cases with two, 40 with three, and 87 with four or more subtasks.

The paper's evaluation set is the full 200-task registry, not a subset selected
by the `split` field. Each of the nine agents is evaluated in two delivery modes
with three repetitions: 200 × 9 × 2 × 3 = 10,800 episodes.

The paper reports 47 separate construction tasks used during benchmark
development, excluded from the evaluation set and all reported results. Those
tasks are not distributed in this release; they are not the registry's 81
`calibration` instances.

## Legacy registry labels

The registry retains the following labels from an earlier repository policy
for compatibility and optional diagnostic filtering. All three groups are
included in the paper experiment manifest; they are not separate calibration,
development, and held-out test partitions for the paper.

| Legacy label | Instances |
|---|---|
| `calibration` | 81 |
| `development` | 30 |
| `test` | 89 |

The original policy assigned cases with recorded episode or pair evidence to
`calibration`, reserved 30 other cases for development, and labeled the remainder
`test`. The recorded rules are preserved as superseded history in
[`dataset-policy.json`](../configs/dataset-policy.json). The referenced evidence
file, `tmp/debug_touched_cases.json`, is not included in this release, so the
assignment history cannot be independently verified from the public package.
These labels do not establish that the full 200-task evaluation set was held
out from development. Documenting them does not resolve any prior exposure.

## Score aggregation

The paper evaluates every task three times in each delivery mode. Within each
repetition, the 25 tasks are averaged for a scenario. The scenario result is the
mean and sample standard deviation of its three repetition-level means, and the
eight scenario means receive equal weight in the overall result. Batched and
Async task success are aggregated separately; DRS is defined only for Async.

Infrastructure-excluded runs never become model failures. Any missing scored
coverage is reported explicitly, and an incomplete scenario is not silently
substituted for the frozen 25-task scenario panel.

## Registry

`data/async-rbench/registry.json` is the only way a case joins the benchmark;
case directories are not discovered on their own. Schema version `2`:

| Field | Meaning |
|---|---|
| `schema_version` | Registry schema version |
| `case_families` | List of registered cases |
| `case_families[].case_id` | Case identifier, matching the directory name under `cases/` |
| `case_families[].benchmark` | Upstream benchmark the case derives from |
| `case_families[].control_prefix` | Prefix for the case's control-flow check ids |
| `case_families[].instances[]` | Registered instances of the case |
| `case_families[].instances[].instance_id` | Instance identifier within the case |
| `case_families[].instances[].path` | Instance path, relative to the case directory |
| `case_families[].instances[].split` | Legacy diagnostic label: `calibration`, `development`, or `test`; not a paper evaluation partition |

## Source binding and limitations

Every public case records its source benchmark and task identity. Rebound cases
also publish content commitments for the source objective and environment; the
acceptance commitment is public while the acceptance truth remains in the judge
bundle. Balanced source counts do not make the 200 cases statistically
independent: multiple asynchronous variants may still share transformation
patterns, applications, or upstream task families. Report both per-theme and
per-source results rather than treating the corpus as 200 IID samples.

The scoring contract itself — the ERC definition and the metrics built on it —
is defined by the accompanying paper and is not restated here.
