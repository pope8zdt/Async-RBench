# Async-RBench expansion-v2 pipeline

## Purpose

The expansion pipeline derives controlled asynchronous-replanning cases from
authoritative tasks and public execution evidence.  It does not require the
source benchmark to have used concurrent subagents: the treatment under study
is precisely the introduction of concurrent subagents and delayed result
delivery into tasks that a blocking single agent can solve.

## Evidence classes

1. `real_model_execution_trace`: action/observation or reasoning/execution
   history from a public benchmark run.  OSWorld and SWE-bench records use this
   class.
2. `official_scenario_configuration`: an official MultiAgentBench task and its
   agent/relationship configuration.  It is a task source, not a trajectory.
3. `public_model_final_output`: a public model answer paired to an official
   MultiAgentBench task.  It can support outcome design, but is not an action or
   interleaving trace.

These labels are immutable through screening and case production.  The
pipeline must never relabel a task configuration or final answer as a real
trajectory.

## Stage order

1. **Source registration and structural agent pre-screen**: register every
   artifact, validate basic evidence availability, deduplicate semantic tasks,
   and retain explicit reject/expand reasons.
2. **Codex semantic initial screen**: the logged-in `gpt-5.6-sol` model judges
   whether a task contains a genuinely delegable subproblem whose result can
   materially alter downstream work.  Ordinary sequential command results do
   not qualify merely by being renamed as subagent results.
3. **Simulated human review**: three separate Codex invocations answer only
   fixed-choice questions.  They use causal-methodology, benchmark-engineering,
   and adversarial-audit lenses.  This is disclosed as proxy review and is not
   represented as real human annotation.
4. **Adjudication**: at least two validated Accept decisions are required.
   Reported choices are recomputed by deterministic rules; a model cannot force
   acceptance by returning an inconsistent free-form decision.
5. **Case production**: accepted blueprints become stable IDs of the form
   `<benchmark>-<semantic-family>-<source-hash>`.  Families follow task
   semantics, never round-robin assignment.
6. **Production gates**: every case must pass ReAct, Linear, and Async oracles
   with no unscored points.  One directed negative variant is executed for
   every score point and must fail its target point.
7. **Leakage audit**: private affected/stale identifiers and expected action
   sets are not placed in the participant prompt.  The participant receives an
   unordered action catalogue and must infer the valid final actions from task
   state and event authority.
8. **Challenge-validity pilot**: a model pilot must have full three-mode
   coverage, at least 10 cases, Linear mean at least 0.80, an Async-minus-Linear
   mean gap of at least -0.03, and Async lower than Linear on at least 30% of
   sampled cases.  These are calibration defaults, not a substitute for a
   larger replicated multi-model experiment.
9. **Final audit**: source/review/production cardinalities, uniqueness, three
   benchmark coverage, upstream revisions, evidence hashes, and empirical
   challenge validity are checked fail-closed.  Either structural or challenge
   failure produces a non-zero exit status.

## Scoring contract

The main score is mode-neutral and identical for ReAct, Linear, and Async:

- 70% is split across the task-specific required post-result actions;
- 10% rejects stale/superseded work;
- 10% rejects unrelated or duplicate work;
- 5% preserves valid prior work;
- 5% requires final-state reverification.

Therefore a task with two required affected actions has six points, while one
with seven affected actions has eleven.  Async event-intake and replanning
process checks are diagnostics and never create main-score points unavailable
to a blocking baseline.

## Promotion policy

There is no fixed production ceiling.  All candidates that pass the structural
gates are compiled, but quantity is not treated as quality.  Artifacts have
three explicit tiers:

1. **screened source candidate**: source fidelity and semantic eligibility are
   established;
2. **runnable preproduction case**: deterministic oracles, mutations, and
   infrastructure coverage pass;
3. **challenge-validated calibration case**: the empirical pilot also passes
   the challenge-validity gate.

Generated capsules remain preproduction candidates until the empirical gate
and the formal repository case schema pass; the pipeline does not silently add
them to `cases/registry.json`.
