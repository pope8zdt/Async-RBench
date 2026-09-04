# Async-RBench

[![Version: 10.0.0](https://img.shields.io/badge/version-10.0.0-blue)](https://github.com/pope8zdt/Async-RBench)
[![Contract: development](https://img.shields.io/badge/contract-development-orange)](evaluation_contract.json)

Async-RBench evaluates whether a main agent can integrate independently completing subagent results and replan after delayed, stale, conflicting, partial, duplicated, failed, or resource-constrained events.

The benchmark runs the same registered instance in two controlled modes:

- `linear`: the baseline execution condition;
- `async`: concurrent subagent execution with evaluator-controlled event delivery.

The fixed kernel owns scheduling, event delivery, private truth, workspace isolation, verification, scoring, and aggregation. The evaluated adapter owns only the main agent and its child agents.

<img width="1200" alt="Async-RBench overview" src="https://github.com/user-attachments/assets/3b2cd2bb-8cee-464f-ab9b-97251d8e93ed" />

> [!IMPORTANT]
> This private collaboration repository contains hidden verifiers, private event truth, and held-out test instances. Do not publish the repository, expose private case paths to evaluated agents, or use test instances for prompt, adapter, threshold, or verifier development.

## Version 10.0.0

The current release surface is:

- contract version: `10.0.0`;
- contract status: `development`;
- dataset: 200 case directories and 201 registered instances;
- split: 82 calibration / 30 development / 89 test;
- execution modes: `linear` and `async`;
- aggregation unit: equal macro-average across the eight event themes;
- official scope: fixed-harness, containerized Track A runs only.

The dataset composition is locked, but the evaluation contract is not yet a frozen leaderboard contract. Development and pilot runs are diagnostic. Do not use `validate --release` until the contract status is explicitly frozen.

Only `(case_id, instance_id)` pairs in [`cases/registry.json`](cases/registry.json) are official registered instances.

## Event themes

Every registered instance belongs to exactly one event theme:

1. `delayed_authoritative_result`
2. `late_or_out_of_order_superseded_result`
3. `partial_then_complete_result`
4. `conflicting_valid_results`
5. `duplicate_or_replayed_completion`
6. `child_failure_or_implicit_error`
7. `task_scope_or_dependency_change`
8. `straggler_under_resource_pressure`

The exact theme definitions and frozen counts are in [`event_taxonomy.json`](event_taxonomy.json). Capabilities are independent multi-label measurements and are not added to event-theme counts.

## Metrics

### Primary metrics

Async-RBench v10.0.0 reports three independent headline metrics:

- `linear_base_task_score`: base-task correctness in Linear mode;
- `async_base_task_score`: base-task correctness in Async mode;
- `async_dynamic_replanning_score`: per-event replanning quality in Async mode, combining evaluator-observed process quality and async outcome quality.

The headline values are theme-equal macro-averages. A theme must satisfy the minimum test-instance coverage gate before entering the official aggregate.

### Supporting metrics

- `paired_bts_delta`: paired Linear minus Async Base Task Score.
- `semantic_task_score`, `linear_semantic_task_score`, `async_semantic_task_score`: frozen programmatic semantic-verifier scores.
- `paired_semantic_drop`: paired Linear semantic score minus Async semantic score.
- `dynamic_control_score`: legacy causal decision-group control score retained for compatibility and diagnosis.
- `dt_score`: secondary compatibility summary, `0.80 * dynamic_control_score + 0.20 * semantic_task_score`.
- `dynamic_success_rate`: share of Async episodes with Dynamic Control Score at least `0.75` and all critical dynamic checks passing.
- `critical_dynamic_success_rate`: share of Async episodes passing every critical dynamic check.
- `dynamic_dimension_scores`: `event_intake`, `state_revision`, `plan_revision`, and `closure` breakdowns.
- `capability_dynamic_control_scores`: dynamic-control breakdown by declared capability category.
- `scenario_construction_rate` and `scenario_exposure_rate`: harness construction and participant exposure diagnostics.
- `stale_retention_rate`, `reverification_completeness`, and `recovery_latency_mean_ms`: replanning-process diagnostics.
- event-opportunity counts: declared, delivered, presented, acted-on, unreached, and designed-terminal opportunities.
- reliability: Async and Linear `pass@1`, `pass@2`, and `pass@3`.
- efficiency: token means/medians/p95, paired Async token delta, mode-separated wall-clock statistics, and cost-quality Pareto rows.
- submission metrics: acceptance/rejection rate, first-attempt and retry acceptance, accepted-child token cost, and extra tokens from public rejections.
- attempt outcomes: token-budget exhaustion, turn-limit exhaustion, no-submission, cancellation, timeout, crash, contract failure, and infrastructure failure rates/counts.
- redelegation metrics: retry attempt count, invalid redelegation count, and invalid redelegation rate.
- integrity diagnostics: scored/unscored counts, leaderboard eligibility, theme coverage, denominator digest consistency, pair completeness, conformance, and hard-fail reasons.

[`evaluation_contract.json`](evaluation_contract.json) is the machine-readable authority for metric definitions. Aggregate field generation lives in [`async_rbench/evaluation/aggregate.py`](async_rbench/evaluation/aggregate.py); component weighting lives in [`async_rbench/evaluation/weighting.py`](async_rbench/evaluation/weighting.py).

## Repository layout

```text
Async-RBench/
|-- async_rbench/           kernel, protocol, runtime, scoring, and audit code
|   |-- evaluation/         runner, scheduler, scoring, aggregation, termination
|   |-- conformance/        adapter protocol conformance suite
|   |-- profiles/           fixed and development adapter profiles
|   `-- protocol_sdk/       JSONL gateway and capability RPC
|-- cases/                  200 case directories plus registry.json
|-- configs/                model profiles, calibration plan, runtime locks
|-- adapters/               executable adapter entry points
|-- schemas/                machine-readable JSON Schemas
|-- scripts/                current audit, batch, and native-runtime utilities
|-- tests/                  framework unit and integration tests
|-- docs/                   runbook and v10 architecture contracts
|-- examples/               simple-review example payloads
|-- research/               event-migration audit manifest used by tests
|-- run_case.ps1            canonical single-instance launcher
|-- evaluation_contract.json
|-- event_taxonomy.json
`-- dataset_policy.json
```

Generated runs belong under `artifacts/experiments/` and are ignored by Git. Optional upstream repositories and native assets belong under `upstream/` and are also excluded.

## Quick start

### 1. Install

Windows PowerShell 7, Python 3.11+, Git, and Docker Desktop with the Linux engine are required.

```powershell
git clone https://github.com/pope8zdt/Async-RBench.git
Set-Location Async-RBench
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
docker info
```

### 2. Validate without model cost

```powershell
python -m async_rbench.cli validate
python -m pytest -q
```

A clean clone may skip author-local tests whose large upstream inputs are intentionally not distributed. It must not report failed or errored tests.

### 3. Choose an instance and profile

Choose a `calibration` or `development` instance from `cases/registry.json`. Do not independently select held-out `test` instances.

Model profiles are under `configs/model-profiles/`. Set the environment variable named by the profile's `api_key_env` field. Example:

```powershell
$env:ASYNC_RBENCH_DEEPSEEK_KEY = Read-Host "DeepSeek API key" -MaskInput
```

Never store credentials in the repository.

### 4. Run one paired case

```powershell
.\run_case.ps1 `
  -Instance "secure-release::seed-1" `
  -Config "configs/model-profiles/deepseek-v4-pro.yaml" `
  -Repetitions 1 `
  -Seed 2026
```

The launcher validates the repository, checks the provider and Docker, creates an immutable manifest, runs paired Linear/Async episodes, aggregates scores, and audits the run.

### Run the frozen 61-case cohort

The repository includes a runnable cohort of 61 existing, registered `seed-1`
instances in `research/experiment-design/paper-eval-existing-61.csv`. It excludes
`gaia2-stockholm-moveout` and does not include any of the 19 planned new cases.

```powershell
.\run_paper_eval_61.ps1 `
  -Config "configs/model-profiles/deepseek-v4-pro.yaml" `
  -Repetitions 1 `
  -Seed 2026
```

This validates the selection, creates one immutable manifest in the CSV's
frozen order, and runs both Linear and Async for all 61 cases. The cohort keeps
the original calibration/development/test labels; it is a reproducible
execution cohort, not a claim that every case is held-out.

To validate the selection without starting an experiment:

```powershell
python -m async_rbench.paper_eval check --root .
```

Outputs are written to:

```text
artifacts/experiments/manual-<case>-<timestamp>/
|-- manifest.json
|-- runs/
|-- results.json
|-- run-audit.json
`-- live.log
```

### 5. Resume an infrastructure-interrupted run

```powershell
.\run_case.ps1 `
  -Instance "secure-release::seed-1" `
  -Config "configs/model-profiles/deepseek-v4-pro.yaml" `
  -ExperimentRoot "artifacts/experiments/manual-secure-release-seed-1-YYYYMMDD-HHMMSS" `
  -Resume
```

Resume only with the original experiment directory, manifest, profile, and commit. Model failures, low scores, timeouts caused by participant behavior, and budget exhaustion are valid outcomes and must not be rerun as infrastructure failures.

## Documentation

- [`docs/CASE_RUNBOOK.zh-CN.md`](docs/CASE_RUNBOOK.zh-CN.md): complete Chinese operator runbook.
- [`PROTOCOL.md`](PROTOCOL.md): benchmark protocol.
- [`ADAPTER_PROTOCOL.md`](ADAPTER_PROTOCOL.md): adapter boundary and JSONL interface.
- [`docs/kernel-contract.md`](docs/kernel-contract.md): fixed kernel responsibilities.
- [`docs/adapter-contract.md`](docs/adapter-contract.md): adapter responsibilities.
- [`docs/async-rbench-result-contract-and-termination.md`](docs/async-rbench-result-contract-and-termination.md): result validation and terminal taxonomy.
- [`docs/evaluation-tracks.md`](docs/evaluation-tracks.md): official and development track separation.

## Repository hygiene

Do not commit API keys, `.env` files, local environments, upstream checkouts, experiment outputs, or private evaluator data copied into participant-visible paths. Keep generated evidence under `artifacts/` and preserve completed experiment directories unchanged.
