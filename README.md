# Async-RBench

[![Version: 10.0.0](https://img.shields.io/badge/version-10.0.0-blue)](https://github.com/pope8zdt/Async-RBench) [![Contract: development](https://img.shields.io/badge/contract-development-orange)](evaluation_contract.json)

Async-RBench is a benchmark for evaluating whether a main agent can integrate independently completing subagent results and dynamically replan after delayed, stale, conflicting, partial, duplicated, failed, or resource-constrained events.

As long-running agents move from sequential tool calls toward concurrent subagent delegation, the main agent must maintain changing task state, revise dependencies, reject stale results, resolve conflicts, and decide when to wait, cancel, restart, or continue. Async-RBench constructs these interrupt-driven situations under controlled Linear and Async execution modes and evaluates both final task quality and evaluator-observed dynamic-control behavior.

<img width="1200" alt="Async-RBench overview" src="https://github.com/user-attachments/assets/3b2cd2bb-8cee-464f-ab9b-97251d8e93ed" />

> [!IMPORTANT]
> This collaboration repository contains private case definitions, hidden verifiers, event truth, and held-out test cases. Keep the repository private, grant access only to approved experimenters, and do not publish, fork publicly, or expose private paths to evaluated agents.

## Start here

The step-by-step Chinese runbook covers cloning, installation, credentials, repository validation, running one paired Linear/Async case, resuming a run, and returning artifacts:

- [Case 运行说明书（中文）](docs/CASE_RUNBOOK.zh-CN.md)

Minimal setup on Windows PowerShell 7:

```powershell
git clone https://github.com/pope8zdt/Async-RBench.git
Set-Location Async-RBench
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
docker info
python -m async_rbench.cli validate
python -m pytest -q
```

Run one registered case as a paired Linear/Async experiment:

```powershell
$env:ASYNC_RBENCH_DEEPSEEK_KEY = Read-Host "DeepSeek API key" -MaskInput
.\run_case.ps1 `
  -Instance "secure-release::seed-1" `
  -Config "configs/model-profiles/deepseek-v4-pro.yaml"
```

The launcher writes the immutable manifest, episode traces, aggregate report, run audit, and live log under `artifacts/experiments/`. That directory is intentionally excluded from Git.

Only `(case_id, instance_id)` pairs listed in `cases/registry.json` are official registered instances. Calibration and development instances may be used for framework verification. Held-out test instances must not be used for prompt, adapter, threshold, or verifier development.

## Version 10.0.0

This release is **Async-RBench 10.0.0**. The dataset composition and Track A statistical design are locked, but the evaluation contract this release certifies is still a **development contract** (see [Evaluation status](#evaluation-status)); a frozen, reportable leaderboard result only becomes available once a release gate is passed against the development-free contract.

## Evaluation status

The dataset composition and Track A statistical design are locked, but the evaluation contract remains a development contract. Pilot runs are diagnostic and cannot be reported as a frozen leaderboard result. In this release the contract version reads **10.0.0**; the repository is a development contract and its runs are an engineering/development benchmark, not a certified product.

- Contract: `10.0.0`, status `development`;
- Dataset: 201 registered target instances — calibration 82, development 30, test 89 (dataset_policy.json);
- Primary Track A outcome: Async Dynamic Control Score;
- Secondary summary: 80% dynamic control + 20% semantic task score.

What is and is not a result right now:

- Pilot and engineering runs are **diagnostic**: they exercise the harness, the adapter protocol, the event taxonomy, and the scoring/aggregation pipeline. They must **not** be reported or quoted as a frozen leaderboard result.
- A run that passes every hard gate (`python -m async_rbench.eval_cli aggregate` and `audit-run` exiting zero, with the conformance gate green) is evidence the *framework* works end-to-end, not that any score is final.
- A frozen leaderboard requires the evaluation contract to leave development and the repository to pass the `--release` certification gate. Do **not** pass `--release` to `python -m async_rbench.cli validate` while the contract is still in development — that gate rejects at certification time and that rejection is not a case failure.

## Repository layout

The repository implements a four-layer harness redesign ("DTbench2"): a fixed kernel, event sourcing, per-model profiles, and a conformance + replay protocol layer. Evaluated agents run inside Docker as isolated adapter processes that talk to the kernel over the protocol SDK.

### Directory breakdown

- `async_rbench/` — Core implementation package: case pipeline modules, runtimes, scoring and the adapter protocol.
  - `async_rbench/evaluation/` — Scoring/weighting/termination/contract/audit engine: `scoring.py`, `weighting.py`, `termination.py`, `runner.py`, `scheduler.py`, `event_store.py`, `model_backend.py`, `calibration.py`, `audit.py`, contract modules.
  - `async_rbench/conformance/` — Layer-4 protocol conformance checks (`suite.py`, `runner.py`) verifying protocol invariants, decoupled from live scoring.
  - `async_rbench/profiles/` — Per-adapter implementations and the profile registry (`profile.py`): `conformance_mock/`, `minimal_api/`, `native_agent/`, `reference_scaffold_api/`.
  - `async_rbench/protocol_sdk/` — SDK between adapter and kernel: `JsonlGateway` (`gateway.py`) and capability RPC (`capability.py`).
- `cases/` — All registered cases: `registry.json` plus one dir per `case_id` (200 case dirs). A registered case carries `public_case.yaml` (participant view), `private/` (`private_case.yaml`, `source_task`, `quality_contract`, `source_lock`, score plans), `task/` (Dockerfile, tests, mutations), `generate.py`/`oracle.py`/`verify.py`, `PROVENANCE.md`, `STATUS.json`; multi-instance cases add `instances/<instance_id>/` overrides. Only `(case_id, instance_id)` pairs in `registry.json` are official.
- `configs/` — Configuration: versioned model profiles plus the calibration plan, native-runtime dependency locks and pipeline-pilot WAL.
  - `configs/model-profiles/` — Versioned `*.yaml` model profiles (`deepseek-v4-*`, `gemini-*`, `gpt-5.4/5.6-*`, `qwen3-*`) selecting model/api and resource knobs for runs.
- `schemas/` — Machine-readable JSON Schemas: adapter-event, candidate-instance, case-ir, decision-point-review, mutation-kill-matrix, quality-contract.
- `adapters/` — Executable adapter entry points for evaluated agent systems; thin re-exports of `async_rbench/profiles/<profile>/adapter.py`.
- `scripts/` — Utilities: case production, marble/OSWorld native-runtime bootstrap & environment qualification, batch/case run scripts, audit and migration helpers.
- `tests/` — Framework unit and integration tests: `conftest.py`, per-feature `test_*.py`, `author_local.py`/`mock_adapter.py` helpers, `verifier_mutations/` fixtures.
- `tools/` — One-off repository utilities (`sanitize_public_cases_v3.py`).
- `docs/` — Runbook and architecture docs: `CASE_RUNBOOK.zh-CN.md` (step-by-step run guide), `kernel-contract.md`, `adapter-contract.md`, `evaluation-tracks.md`, environment smokes, superpowers/plans.
- `examples/` — Worked example payloads for the simple-review flow (`examples/simple-review/`).
- `artifacts/` — Run and migration outputs: `experiments/` (per-run manifests, traces, reports — gitignored), `native-runtime-v4/`, `conformance-mock/`, contract-migration JSONs; **not for source control**.
- `upstream/` — Optional external source/native material intentionally not tracked in Git (only `README.md` present).
- `research/` — Experiment-design artifacts: `experiment-design/` manifest plus instance-registry scan utilities.
- `cal-gemini-fix-20260902-0350/` — Calibration scratch directory (currently empty).

### Annotated tree

```text
async-rbench-redesign/                  Repo root — Async-RBench benchmark ("DTbench2" 4-layer harness redesign)
├── async_rbench/                       Core implementation package (kernel, evaluation, adapter protocol)
│   ├── spec.py                         Case/instance/registry spec dataclasses (registry "case_families" note lives here)
│   ├── cli.py                          Validator entry point (python -m async_rbench.cli validate)
│   ├── eval_cli.py                     Evaluation-run CLI (make-manifest / run-manifest / aggregate / audit-run / conformance / score)
│   ├── case_factory.py                 Fail-closed promotion gate for reviewed case instances
│   ├── case_ir.py                      Task-causal Case IR + case-specific score-plan compiler
│   ├── case_runtime.py                 Stable runtime API for generated Docker-backed case packages
│   ├── case_quality.py / dynamic_points.py / dynamic_pilot.py / pipeline_pilot.py / provenance.py / source_fidelity.py ...   case / provenance / quality pipeline modules
│   ├── marble_runtime.py / osworld_runtime.py / docker_case.py / native_runtime_registry.py   execution runtimes
│   ├── evaluation/                     Scoring / contract / termination / audit engine subpackage
│   ├── conformance/                    Layer-4 protocol conformance checks (suite.py, runner.py)
│   ├── profiles/                       Harness-side per-profile implementations + profile.py registry
│   └── protocol_sdk/                   JsonlGateway + capability RPC between adapter process and kernel
├── cases/                              200 registered case dirs + registry (participant-visible public + evaluator-only private)
│   ├── registry.json                   schema-v2 registry: official (case_id, instance_id) pairs, paths, splits
│   └── secure-release/, mab-*/, osw-*/, swe-*/, tbn-*/, gaia2-stockholm-moveout/, git-conflict-and-cleanup-closure/, scheduler-selective-replan/, swe-bench-selective-patch/, data-recovery-service/, distributed-model-runtime/
├── configs/
│   ├── model-profiles/                 Versioned per-model *.yaml profiles (model, api, cost, resource knobs)
│   ├── calibration-plan.json           Calibration experiment plan (calibration is file-based here, not a subdir)
│   ├── marble-native-requirements.lock / osworld-native-requirements.{in,lock}   native-runtime dependency locks
│   └── pipeline-pilot-wal.json         Pipeline-pilot write-ahead-log state
├── schemas/                            Machine-readable JSON Schemas (adapter-event, case-ir, quality-contract, ...)
├── adapters/                           Thin executable adapter entry points an evaluated agent system launches (thin re-exports of async_rbench/profiles/*)
├── scripts/                            Case production, native-runtime bootstrap, batch-run and audit utilities
├── tests/                              Framework unit + integration tests (conftest.py, test_*.py, verifier_mutations/)
├── tools/                              One-off utilities (sanitize_public_cases_v3.py)
├── docs/                               Runbook + architecture / environment docs (CASE_RUNBOOK.zh-CN.md, kernel-contract.md, ...)
├── examples/simple-review/             Simple-review annotation example payloads (demo json/jsonl)
├── artifacts/                          Run outputs — experiments/ (gitignored), native-runtime-v4/, conformance-mock/, contract-migration JSONs
├── upstream/                           Optional external source/native material; not tracked in Git (only README.md present)
├── research/                           experiment-design manifest + instance-registry scan utilities
├── cal-gemini-fix-20260902-0350/       Calibration scratch dir (currently empty)
│
├── evaluation_contract.json            Evaluation contract: execution modes (linear/async), capability categories, event themes, resource policy
├── event_taxonomy.json                 Event taxonomy — 8 case-family/theme definitions and counting rules
├── dataset_policy.json                 Dataset policy — 201 registered target instances, calibration/development/test split rules
├── run_case.ps1 / run_calibration.ps1 / run_qwen_family_sample.ps1   Windows launchers for runs
├── pyproject.toml / pytest.ini / uv.lock Package + test config and lockfile
├── ADAPTER_PROTOCOL.md / PROTOCOL.md / EXPERIMENT.md / REFERENCE_SCAFFOLD.md / README.md   Top-level spec docs
└── .venv/ / .pytest_cache/ (gitignored) local environment noise
```

### Selected files

| File | Purpose |
|---|---|
| `async_rbench/spec.py` | Case/instance/registry spec dataclasses and loading; records the schema-v2 `case_families` compatibility semantics |
| `async_rbench/cli.py` | Repository validator CLI (`python -m async_rbench.cli validate`) |
| `async_rbench/evaluation/weighting.py` | Single source of truth for component/capability weighting and category scoring |
| `async_rbench/evaluation/termination.py` | Mutually exclusive per-attempt terminal/outcome classification |
| `async_rbench/evaluation/scoring.py` | Score aggregation/decoupling gate logic used by the scoring domain registry |
| `async_rbench/conformance/suite.py` | Layer-4 protocol conformance checks over recorded episode events |
| `async_rbench/protocol_sdk/gateway.py` | `JsonlGateway` used to instrument adapter lifecycle hooks and delivery |
| `async_rbench/profiles/profile.py` | Profile model: defines `PROFILE_TYPES` and `RUNTIME_MODES` constants across adapter profiles |
| `adapters/minimal_api.py` | Representative adapter entry point re-exporting `async_rbench/profiles/minimal_api/adapter.py` main |
| `cases/registry.json` | schema-v2 registry of registered cases and their immutable instances (paths, splits, control prefixes) |
| `cases/secure-release/public_case.yaml` | Representative participant-visible public case definition of a registered case (paired `private/` side is evaluator-only) |
| `configs/model-profiles/deepseek-v4-pro.yaml` | Representative versioned model profile used by `run_case.ps1` (e.g. paired Linear/Async runs) |
| `configs/calibration-plan.json` | Calibration experiment plan (calibration configuration lives as a file here, not a subdirectory) |
| `evaluation_contract.json` | Evaluation contract: execution modes (linear/async), capability categories, event themes, status |
| `event_taxonomy.json` | Event taxonomy defining the eight case-family/theme categories and counting rules |
| `dataset_policy.json` | Dataset policy: 201 target registered instances with calibration/development/test split rules |
| `run_case.ps1` | Windows launcher to run one registered case (Instance + Config) writing immutable manifest/traces under `artifacts/experiments/` |
| `run_calibration.ps1` | Windows launcher driving preflight / smoke / calibration empirical runs against a hardcoded model profile + key env var (it does **not** read `configs/calibration-plan.json` — that file is validated only by `python -m async_rbench.cli validate`) |
| `docs/CASE_RUNBOOK.zh-CN.md` | Step-by-step Chinese runbook: clone, install, validate, run paired Linear/Async case, resume, return artifacts |
| `pyproject.toml` | Package metadata and test extras for the `async_rbench` install (editable install used by the runbook) |

Terminology: **case family** means one of the eight `primary_event_theme` categories. `case_id` identifies a registered case within a family, and `instance_id` identifies one immutable instance. The registry key `case_families` is retained only as a legacy schema-v2 field; its entries are registered cases, not the eight families.

## Running a case

This section is a self-contained tutorial for launching real, model-backed runs on Windows. All `.ps1` launchers must be run from the **repo root** (`F:/DTbench/DTbench2/.claude/worktrees/async-rbench-redesign` on this host — scripts `Set-Location` to `$PSScriptRoot`, but `artifacts` paths resolve from the launch directory). Everything under `artifacts/` and `*.log` is gitignored: experiment outputs must never be committed.

### Prerequisites

1. **Activated venv whose bare `python` resolves to `.venv`.** `run_case.ps1` / `run_calibration.ps1` invoke **bare `python`** (not the venv exe), and that interpreter must have `yaml`/`jsonschema` plus the editable `async_rbench` install. Setup:
   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e ".[test]"
   ```
   (`run_qwen_family_sample.ps1` instead prepends `.venv\Scripts` to `$env:PATH` so bare `python` resolves to the venv.)

2. **Docker Desktop running the LINUX container engine**: `docker` must be on `PATH` and `docker info --format '{{.ServerVersion}}'` must succeed. Both `run_case.ps1` and `run_calibration.ps1` hard-fail the launch otherwise. Official runs force container isolation, so the engine is mandatory.

3. **Provider API key set in the current PowerShell process**, in the env var named by the profile's `api_key_env` field. `deepseek-v4-flash.yaml` and `deepseek-v4-pro.yaml` both use `ASYNC_RBENCH_DEEPSEEK_KEY`. `run_case.ps1` runs a provider preflight before **any** paid episode and throws if the key is missing/malformed (it must be a flat bearer token — no whitespace/non-ASCII). Set it with:
   ```powershell
   $env:ASYNC_RBENCH_DEEPSEEK_KEY = Read-Host "DeepSeek API key" -MaskInput
   ```
   Never write the key into the repo. (Relay-operator variant: key stored in an `APIKey.txt` and loaded into env before launching.) Other profiles name their own env var — `POLO_GEMINI_API_KEY`, `GEMINI3_FLASH_API_KEY`, `OPENAI_API_KEY`, `QWEN3_CODER_API_KEY`, `DASHSCOPE_API_KEY`, `QWEN35_27B_API_KEY` — see the profile YAML. `codex_cli` profiles use no env key (auth delegated to a logged-in Codex CLI).

4. **A model profile YAML** at `configs/model-profiles/*.yaml` whose resource fields **exactly match** the frozen resource policy in `evaluation_contract.json` (`max_api_concurrency` 4, `episode_timeout_sec` 2400, `gateway_grace_sec` 15, budgets main 5e5/5e5/1e6, `max_child_turns` 40, `max_total_child_spawns` 5, etc.). `run_case.ps1` always launches with `--official-track`, and `validate_official_resource_policy` raises `ValueError` on **any** drift, so the episode fails at launch if you lower them.

5. **The repo passes `python -m async_rbench.cli validate`** — `run_case.ps1` re-runs it on every launch and throws on failure. Development runs do **not** need `--release`; that gate only applies to a frozen contract.

### Run one registered case (paired Linear/Async)

```powershell
# Repo root. One PowerShell process:
$env:ASYNC_RBENCH_DEEPSEEK_KEY = Read-Host "DeepSeek API key" -MaskInput
.\run_case.ps1 -Instance "secure-release::seed-1" -Config "configs/model-profiles/deepseek-v4-flash.yaml"
```

`run_case.ps1` full parameter list:

| Parameter | Meaning |
|---|---|
| `-Instance` | Required, pattern `^[^:]+::[^:]+$`, e.g. `"mab-late-test-evidence-4c6c77884e::seed-1"` (development) or `"secure-release::seed-1"` (calibration) |
| `-Config` | Required — path to a model-profile YAML (absolute or repo-relative); must match the resource policy |
| `-Repetitions` | `int` 1..10, default 1 |
| `-Guidance` | `none` \| `protocol` \| `incentive`, default `incentive` |
| `-Seed` | `int`, default 2026 |
| `-ExperimentRoot` | path; default auto `artifacts/experiments/manual-<sanitizedInstance>-<yyyyMMdd-HHmmss>` |
| `-Resume` | switch |
| `-EpisodeTimeout` | `int` 60..14400, default 2400 (must equal frozen 2400 under official track) |
| `-ProgressHeartbeat` | `int` 5..300, default 20 |

**Flow it runs:** provider preflight → read `main_model` → `python -m async_rbench.cli validate` → Docker check → `make-manifest` (`--repetitions --guidance --seed --execution-modes linear async --instances <Instance> --model <main_model>`, so **one paired case = 2 × Repetitions episodes**) → `run-manifest` (`--profile reference_scaffold_api --config <Config> --output runs --timeout --progress-heartbeat --official-track`) → `aggregate` → `audit-run`. **Single-mode runs are not possible**: the launcher always builds the linear + async pair.

More examples:

```powershell
# One pair, defaults
.\run_case.ps1 -Instance "secure-release::seed-1" -Config "configs/model-profiles/deepseek-v4-flash.yaml"

# 3 repeats, custom seed + root (development-split instance)
.\run_case.ps1 -Instance "mab-dependency-unblock-8b943d725b::seed-1" `
  -Config "configs/model-profiles/deepseek-v4-flash.yaml" `
  -Repetitions 3 -Seed 2026 -ExperimentRoot "artifacts\experiments\myrun"
```

### Batch across the registry

```powershell
python scripts/run_batch_parallel.py [--out artifacts/experiments/batch-results.jsonl] [--jobs N] [--stop-flag batch-stop.FLAG] [--only-file FILE]
```

- Enumerates every instance in `cases/registry.json` (or the lines of `--only-file`, one `case_id::instance_id` per line; `--jobs N` keeps only the first N) and fans them over **hardcoded LANES** (two DeepSeek lanes `dsA`/`dsB`, both on `configs/model-profiles/deepseek-v4-flash.yaml` with env key `ASYNC_RBENCH_DEEPSEEK_KEY`). Each lane pulls from one shared queue so faster work drains.
- Each instance is spawned as `powershell.exe -NoProfile -ExecutionPolicy Bypass -File run_case.ps1 -Instance <i> -Config <profile> -Repetitions 3 -ExperimentRoot artifacts/experiments/batch-<lane>-<sanitizedInstance>-<ts>-<seq>` — **each process gets a UNIQUE root**; the driver always overrides repetitions to 3.
- Fails fast if a lane env key is unset. Per-instance subprocess timeout **2h**. Stop = create the `--stop-flag` file or SIGINT; workers finish the current instance then stop pulling.
- Writes one JSONL summary (default `artifacts/experiments/batch-results.jsonl` — one JSON object per instance: `lane`, `exit`, scored/unscored summary, `exp_root`) plus the per-instance experiment dirs.
- Note: LANES/profile/repetitions are hardcoded at the top of the file, and the **registry** (not the split) drives selection.

### Calibration family

```powershell
.\run_calibration.ps1 [-Mode preflight|smoke|calibration] [-ApiBaseUrl https://api.deepseek.com] [-ExperimentRoot ...] [-Resume] [-EpisodeTimeout 2400] [-ProgressHeartbeat 20]
```

- Uses `deepseek-v4-pro`, profile `configs/model-profiles/deepseek-v4-pro.yaml`, key env `ASYNC_RBENCH_DEEPSEEK_KEY`, default root `artifacts/experiments/deepseek-v4-pro-<Mode>-<ts>`.
- `preflight`: repo validate + one small paid function-tool probe (no benchmark episode). `smoke`: `secure-release::seed-1` once per mode (2 episodes). `calibration`: is a **full-corpus** run — the launcher passes no `--instances`/split filter, so `make-manifest` enumerates every registered instance at `--repetitions 3` × 2 modes (currently 201 × 3 × 2 = 1206 episodes). To calibrate a single case instead, drive it with `run_case.ps1`.
- Same `make-manifest` → `run-manifest` (`--official-track`) → `aggregate` → `audit-run` pipeline. Sets `ASYNC_RBENCH_MODEL_API_URL` / `_API_KEY_ENV` / `_MAIN_MODEL` / `_CHILD_MODEL` env overrides on top of `--config`.

### Resume an interrupted run

Resume an interrupted `run_case.ps1` experiment against the **existing** experiment directory (`run_case.ps1` requires `-ExperimentRoot` when `-Resume` is set and refuses if `manifest.json` is missing):

```powershell
.\run_case.ps1 -Instance "case_id::instance_id" `
  -Config "configs/model-profiles/deepseek-v4-flash.yaml" `
  -ExperimentRoot "artifacts\experiments\manual-<case>-<yyyyMMdd-HHmmss>" `
  -Resume
```

- It does **not** regenerate a manifest. `run-manifest --resume` skips episodes whose `runs/<episode_id>/score.json` already exists and is digest-matched (manifest sha, source/scaffold digest, contract version+sha, verifier bundle, case sha are all rechecked; **any drift aborts the resume**).
- **Only infrastructure failures are resumable**; model failures / low scores / budget exhaustion are valid scored outcomes and must not be rerun.
- Output is Tee'd to `resume.log` (instead of `live.log`), then `aggregate` + `audit-run` rerun.
- Calibration equivalent: `.\run_calibration.ps1 -Mode calibration -Resume -ExperimentRoot "artifacts\experiments\deepseek-v4-pro-calibration-<ts>"`.
- Lower-level `eval_cli` resume: `python -m async_rbench.eval_cli run-manifest --manifest <manifest.json> --output <runs dir> --profile reference_scaffold_api --config <profile.yaml> --official-track --resume`.

### Audit and aggregate (what the launchers run for you)

```powershell
python -m async_rbench.eval_cli audit-run --root <runs dir> --output <run-audit.json>
```

- `--root` is the `runs/` subdirectory (per-episode `score.json` dirs), **not** the experiment root; the `run-audit.json` default location is `<ExperimentRoot>/run-audit.json`.
- `audit-run` cross-checks every episode's recorded case/scaffold/evaluation-contract digests against the **current tree**, computes contract fixtures, and exits nonzero unless **all** gates pass: `contract_fixtures_passed`, `episodes_present`, `artifact_digests_match_current`, `manifest_complete` (planned ids from the sibling `manifest.json` ≤ audited), and no hard-fail reason (`contract_fixture_failure` / `hidden_submission_constraint` / `private_submission_rejection` / `unknown_child_terminal` / `official_linear_zero_main_tokens`).
- `run_case.ps1` / `run_calibration.ps1` invoke this automatically at the end (`python -m async_rbench.eval_cli audit-run --root $runs --output $audit`) and throw if it exits nonzero.
- `audit_run()` also runs a **full-corpus** contract-fixture audit over all discovered case instances (subprocess-heavy, several minutes) regardless of how many episodes the run actually has — do not mistake the delay for a hang.

Related: `python -m async_rbench.eval_cli aggregate --root <runs dir> --manifest <manifest.json> --output <results.json>` — auto-run by the launchers; exits nonzero on its own hard_fail.

### What lands where

| Artifact | Meaning |
|---|---|
| `<ExperimentRoot>/manifest.json` | Immutable manifest (`manifest_version 4.0`) written by `make-manifest`; pins seed/repetitions/guidance/model/split, `evaluation_contract_version`+sha256, `verifier_bundle_sha256` and `case_bundle_sha256` per registered instance, and `episodes[]` (one per mode: `episode_id` like `<case>-<repeat>-<mode>-<8hex>`, `case_id`, `instance_id`, `repeat`, `execution_mode` `linear`\|`async`, `counterfactual_pair_id`) |
| `<ExperimentRoot>/runs/<episode_id>/` | Per-episode artifact dir: `score.json` (scored record + provenance digests), `trace.jsonl`, `event_source.jsonl` (audit/scoring source), `participant_trace.jsonl` |
| `<ExperimentRoot>/runs/.conformance/` | Adapter conformance-gate output written under the run output root before episodes start |
| `<ExperimentRoot>/results.json` | Aggregate report from `aggregate --root runs --manifest manifest` (auto-run) |
| `<ExperimentRoot>/run-audit.json` | `audit-run` report (auto-run; hard gates set the exit code) |
| `<ExperimentRoot>/live.log` | Tee-Object of the whole `run-manifest` subprocess stdout+stderr; named `resume.log` when launched with `-Resume` |

Default roots: `artifacts/experiments/manual-<sanitizedInstance>-<yyyyMMdd-HHmmss>` (`run_case`), `artifacts/experiments/batch-<lane>-<instance>-<ts>-<seq>` (batch driver), `artifacts/experiments/deepseek-v4-pro-<Mode>-<ts>` (calibration). The batch driver additionally writes `artifacts/experiments/batch-results.jsonl`.

`artifacts/` and `*.log` are gitignored — experiment outputs must never be committed. Return to the operator as a zip of the full experiment dir + SHA-256.

### Gotchas

- **Bare `python` trap**: `run_case.ps1` and `run_calibration.ps1` call `python` (not the `.venv` exe) for preflight, yaml read, `make-manifest`, `run-manifest`, `aggregate`, `audit-run`. If `.venv` is not activated, `python` resolves to an interpreter without `yaml`/`jsonschema`/`async_rbench` and every stage fails. `run_case.ps1` also spawns the adapter via `sys.executable` (the venv interpreter) at run time.
- **Concurrent launches need a UNIQUE `-ExperimentRoot` per process.** Auto-named roots use second-resolution timestamps + sanitized instance, so two `run_case.ps1` launched in the same second for the same instance collide: manifest-already-exists throw / Tee lock on `live.log`. Each parallel/batch process must pass its own `-ExperimentRoot` (`run_batch_parallel.py` already does).
- **Official-track resource policy is hard-pinned**: `run_case.ps1` always passes `--official-track`, which forbids `--adapter-command`/`--skip-conformance`/`--no-container` and runs `validate_official_resource_policy` — the profile's `max_api_concurrency` etc. **and** the episode timeout (must be 2400) must exactly match `evaluation_contract.json` or launch raises `ValueError` before any episode.
- **Key must be set in the env var the profile names** (`api_key_env`) and be a flat bearer token. `run_case.ps1` provider-preflights and throws on missing/whitespace/non-ASCII key so the run does not burn itself as a 401. Never write keys into the repo (gitignored paths `configs/local/`, `apikey.txt`, `.env` are the only exceptions).
- **Provider relay `47.109.111.28:3000` has been observed down/429/502/timeout** — under it episodes all land as `infrastructure_crash` (hard_fail stays false). Prefer the direct official API base URL; the relay only needs a key in env too.
- **Resume is ONLY for infrastructure failures**: rerunning a low scored episode is forbidden. Resume must reuse the original directory/manifest/config/commit; `run-manifest` rejects any digest drift and only completes episodes lacking a matching `score.json`.
- **`run_case.ps1` refuses to start** when the manifest already exists at `-ExperimentRoot` unless `-Resume` is given; `-Resume` without `-ExperimentRoot` throws.
- **Editing anything** (case files, `evaluation_contract.json`, the profile, prompts) after manifest creation is rejected at `run-manifest` start (contract version/sha + case + verifier digest drift checks) and again at `audit-run` (current-tree digest mismatch makes `artifact_digests_match_current` fail).
- **The `audit-run` step scans and audits ALL discovered case instances** (contract fixtures, subprocess-heavy ~3–4 min) even for a 2-episode run; do not mistake the delay for a hang. `audit-run` and `aggregate` exit nonzero on their hard gates, and `run_case.ps1` throws on that.
- **This host runs Windows PowerShell 5.1**: `Read-Host -MaskInput` and `&&` chaining are unavailable (the qwen sample shows a 5.1 fallback), and driver/launcher scripts must be ASCII-only because PS 5.1 ANSI mangles non-ASCII (Chinese) paths — edit the `.ps1`/`.py` launchers carefully.
- **A batch lane's instance subprocess is capped at 2h** (`subprocess.run` timeout in `run_batch_parallel.py`); a longer single case reports `TIMEOUT` for that lane while the others continue. Batch always forces `-Repetitions 3` regardless of `run_case`'s default of 1.
- **Each episode is its own Docker containerized workspace**; output dirs and case images need ~30 GB+ free disk (runbook guidance) and Docker must stay on the Linux engine for the whole run.

## Protocol references

- [Evaluation protocol](PROTOCOL.md)
- [Adapter protocol](ADAPTER_PROTOCOL.md)
- [Reference scaffold](REFERENCE_SCAFFOLD.md)
- [Evaluation contract](evaluation_contract.json)
- [Dataset policy](dataset_policy.json)
- [Evaluation tracks (Track A design)](docs/evaluation-tracks.md)

Never place API keys, `.env` files, model credentials, experiment outputs, or participant-visible copies of private evaluator data in Git.
