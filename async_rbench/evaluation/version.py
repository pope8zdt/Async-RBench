from __future__ import annotations


# Bump only when the executable evaluation semantics, verifier bundle, or
# reported metric definitions change. Manifests pin this value.
# 6.0.0-dev: the benchmark auto-assigns and auto-starts the initial concurrent
# wave (scenario construction). The model is scored on the subsequent wait,
# cancel, result selection, integration, recovery redelegation, rebuild and
# reverification. scenario_entry is a benchmark-execution audit
# (scenario_constructed), no longer a check of whether the model proactively
# spawned. Applicable points and denominators are frozen per execution mode;
# all models under the same mode share the same denominator digest. Model
# inaction fails the registered point and is never not_applicable. Only
# infrastructure failure to construct an opportunity makes an episode unscored.
# X is not comparable to 5.x runs.
# 6.1.0-dev: child completions are validated against evaluator-owned semantic
# workstream contracts before delivery. Invalid completions resolve on the
# original schedule as result_rejected, cannot be consumed or enter lineage,
# and remain scored model outcomes rather than infrastructure failures.
# 6.2.0-dev: semantic workstream contracts and frozen outcome tests require
# exact merge/conflict content instead of self-consistency alone. Every child
# terminal capability call also produces kernel-private start/finish audit
# events with the complete command, exit code and output.
# 6.2.1-dev: every child, including a replacement child, receives the frozen
# participant-visible artifact schema for its workstream. This closes the gap
# where the main task described an exact JSON shape but isolated children saw
# only a lossy task summary and had to guess field nesting/names.
# 6.3.0-dev: semantic/control becomes an observation dimension only. Frozen X
# weights derive solely from research relevance tiers, with base completion
# retained at the lowest tier and capped as aggregate score mass.
# 6.3.1-dev: each legacy condition may schedule a declared result kind only once,
# matching the one-completion-per-workstream runtime topology. Redelegation is
# measured from explicit initial_wave=False replacement spawns; contract-
# rejection recovery and child-path promotion outcomes are auditable.
# 6.3.2-dev: the reference runtime emits promotion outcomes through its actual
# ProtocolEmitter interface. Every promotion action must close with exactly one
# outcome event; incomplete, duplicate, or orphaned outcome audit makes the
# episode unscored instead of contaminating model-performance results.
# 7.0.0-dev: clean-break benchmark architecture. The five synthetic conditions
# are replaced by paired ``linear`` and true ``async`` execution modes. Cases
# carry capability categories; async results are released in real completion
# order. Participant and evaluator contracts are physically separated, private
# delivery truth is stored only in kernel-private events, and only the fixed
# Track A harness is eligible for the official leaderboard. Benchmark-owned
# initial work uses a separate bounded concurrency ceiling; participant early
# termination is a scored exposure failure, not scenario-construction failure.
# 7.1.0-dev: event stimuli and measured capabilities are separate contract
# dimensions. Every case declares one private primary event theme, optional
# secondary themes and one async scenario class. The kernel can replay an
# already delivered completion after first consumption without inventing a
# child completion; replay truth remains private. Source trajectories are
# provenance/discovery evidence only and are explicitly outside scoring.
# 7.2.0-dev: case families and immutable instances are separate execution
# identities. The registry explicitly enumerates instances; manifests pin both
# verifier and complete case-bundle digests per family/instance. Pairing and
# resume are instance-scoped, while headline macro-averaging remains family-
# balanced so large families cannot dominate the benchmark.
# 8.0.0-dev: dynamic control becomes the primary benchmark construct. Semantic
# task correctness is preserved unchanged as a separately reported component;
# the secondary DTScore assigns 80% mass to a four-stage dynamic macro and 20%
# to semantics. Linear/async comparisons use paired semantic retention rather
# than subtracting unlike mixed denominators. Denominator digests bind policy,
# type, dimension, weight and criticality.
# 9.0.0-dev: authoring and scoring move from fixed lifecycle-stage mass to a
# task-causal Case IR. Eight event policies compile task-specific causal
# decision groups, directional mutations and outcome anchors. Lifecycle stages
# remain diagnostics; the primary dynamic score macro-averages independent
# decision groups. V4-V6 registries remain readable for historical runs.
# 9.1.0-dev: dynamic-score qualification is strictly benchmark-owned. Missing
# participant exposure, rejected authority results and unrealised cancellation
# opportunities remain scored failures and are reported separately from true
# infrastructure qualification errors. Causal root events bind directly to the
# authority-bearing gateway delivery. Semantic anchors remain diagnostic and no
# longer double-penalise independently observable control-flow decisions.
# 10.0.0: release-branch version-number bump that unifies the package and
# evaluation-contract axes. The contract remains a development contract (not
# frozen) --- a frozen leaderboard still requires ``validate_frozen_release``
# to pass, which it will not until both the contract status and the dataset
# policy move to a frozen post-calibration state.
# 10.1.0: fixed model-step horizons replace token-pool admission. Explicit
# finish is immediately terminal, actual tokens are diagnostics, and only the
# high shared emergency fuse produces an unscored resource_safety_abort.
# 10.1.1: participant-controlled non-exposure contributes event DRS=0 instead
# of shrinking the dynamic denominator. The shared emergency fuse is reduced
# to 5,000,000 actual provider-reported tokens per episode.
EVALUATION_CONTRACT_VERSION = "10.1.1"
EVALUATION_CONTRACT_STATUS = "development"
