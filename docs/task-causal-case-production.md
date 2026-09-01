# Task-causal case production

The production unit is not an event template or a trajectory. It is a reviewed
task-causal Case IR compiled into one immutable benchmark instance.

## Pipeline

1. **Screen** source trajectories for an independently arriving observation,
   prior relevant work, a necessary policy change and an observable consequence.
2. **Review** a blind evidence card. Simulated reviews may exercise mechanics but
   always set `promotion_eligible=false`.
3. **Build the Case IR** in `private/case_ir.json`: public task requirements,
   dependency graph, before/after event state, affected dependency closure,
   preservation boundary and task-specific decision contracts.
4. **Compile the score plan** in `private/score_plan.json`. The primary event
   theme supplies required obligations and mutation families; task requirements
   and graph nodes supply the actual subjects and outcome anchors.
5. **Write the V7 registry**. Lifecycle stages are diagnostic tags. Dynamic
   score mass is equal across independent causal decision groups, then the
   benchmark macro-averages cases/families.
6. **Attack the verifier**. Every dynamic point has one directional mutation
   specification, declared target failures and at least one `must_still_pass`
   locality assertion. Release qualification must execute those assertions;
   compilation alone is only a structural gate. Canonical and non-canonical
   correct solutions must pass.
7. **Qualify runtime reachability**. Gateway-only authorities use evaluator-owned
   result-role boundaries. Participant artifact commits can be scored
   preconditions but cannot decide whether an episode is scored.
8. **Calibrate** on real models. Report semantic score in both modes, async
   dynamic score, decision-group diagnostics, stage diagnostics, cost, exposure
   and denominator digests.

## Eight authoring policies

`async_rbench/event_policies.py` freezes the eight primary event themes and only
their minimum causal obligations/mutation families. It does not declare model
capabilities or a fixed point list. A case with no meaningful task-specific
binding is rejected instead of receiving synthetic lifecycle points.

## Pilot command

```powershell
python -m async_rbench.cli dynamic-pilot-build `
  --output artifacts/task-causal-pilot-v7
```

The command creates screening evidence, a disclosed simulated-review stage,
Case IRs, score plans and three non-promotable case bundles. Use
`dynamic-pilot-pair` for one real-model linear/async pair and
`dynamic-pilot-audit` after the requested model runs exist under
`05-runs/gpt54/` and `05-runs/deepseek/`.

## Scoring

For V7 registries:

```text
point_pass = process_evidence AND local_outcome_anchors
decision_group_score = weighted mean(points in the group)
D_case = mean(decision_group_scores)
S_case = mean(task_requirement_group_scores)
```

Critical-point failure still fails dynamic success. The optional secondary
summary remains `DTScore = 0.80 D + 0.20 S`. V4-V6 registries retain their
historical scoring path for reproducibility.
