<div align="center">

# Async-RBench

### Benchmarking asynchronous result integration and dynamic replanning

[![Version](https://img.shields.io/badge/version-11.0.0-2f6f9f)](https://github.com/pope8zdt/Async-RBench)
[![Contract](https://img.shields.io/badge/evaluation%20contract-frozen-2f855a)](evaluation_contract.json)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)](pyproject.toml)
[![Website](https://github.com/pope8zdt/Async-RBench/actions/workflows/pages.yml/badge.svg)](https://github.com/pope8zdt/Async-RBench/actions/workflows/pages.yml)

[Website](https://pope8zdt.github.io/Async-RBench/) ·
[Leaderboard](https://pope8zdt.github.io/Async-RBench/leaderboard/) ·
[Run the benchmark](https://pope8zdt.github.io/Async-RBench/evaluate/) ·
[Documentation](https://pope8zdt.github.io/Async-RBench/docs/)

If Async-RBench is useful to your research, consider starring the repository.

</div>

## 📣 Latest News

- **September 2026:** The public website, DRS/BTS leaderboard, local-run workflow, and reviewed result submission path are available.
- **Track B:** Claude Code, Codex CLI, LangGraph, OpenAI Agents SDK and custom harness components are available as a development track.
- **Version 11.0.0:** The evaluation contract is frozen for reproducible Track A experiments.

## 💡 Overview

Async-RBench evaluates whether a main agent can integrate independently completing subagent results and revise its plan when results arrive late, out of order, partially, repeatedly, in conflict, or under failure and resource pressure.

The same task runs in two controlled modes:

- **Linear:** a baseline execution condition.
- **Async:** concurrent subagent execution with evaluator-controlled event delivery.

The fixed evaluation kernel owns scheduling, event delivery, private truth, workspace isolation, verification, scoring, and aggregation. The evaluated adapter owns the main agent and its child agents. No fixed child-model pool is required.

<p align="center">
  <img width="1200" alt="Async-RBench framework: paired runs, asynchronous execution, and BTS/DRS evaluation" src="docs/assets/async-rbench-framework-v11.png" />
</p>

<p align="center">
  <a href="docs/assets/async-rbench-framework-v11.png">High-resolution PNG</a> ·
  <a href="docs/assets/async-rbench-framework-v11.svg">Editable SVG</a> ·
  <a href="docs/assets/async-rbench-framework-v11.pdf">Vector PDF</a>
</p>

## ✨ Benchmark Highlights

- **201 high-quality tasks** across eight asynchronous event themes.
- **Paired execution** compares the same registered task under Linear and Async conditions.
- **Controlled delivery** makes delayed, stale, conflicting, partial, duplicate, failed, and resource-constrained events reproducible.
- **Independent measurements** separate base-task correctness from dynamic replanning quality.
- **Local execution** keeps credentials, raw traces, and restricted evaluator materials on the participant's machine.
- **Static public leaderboard** publishes aggregate results without requiring a hosted evaluation server.
- **Agent-system evaluation** runs maintained frameworks or custom harness components through the same evaluator boundary.

## 🚀 Quick Start

### 1. Install

Async-RBench requires Windows PowerShell 7, Python 3.11+, Git, and Docker Desktop with the Linux engine.

```powershell
git clone https://github.com/pope8zdt/Async-RBench.git
Set-Location Async-RBench

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
docker info
```

### 2. Validate the checkout

Validation does not call a model.

```powershell
python -m async_rbench.cli validate --release
python -m pytest -q
```

### 3. Configure a model

Use the [configuration generator](https://pope8zdt.github.io/Async-RBench/evaluate/) or add an OpenAI-compatible model profile under `configs/model-profiles/`. Store only the API-key environment-variable name in the profile; keep the key outside the repository.

```powershell
$env:MODEL_API_KEY = Read-Host "API key" -MaskInput
```

### 4. Run one paired task

```powershell
.\run_case.ps1 `
  -Instance "secure-release::seed-1" `
  -Config "model-config.yaml" `
  -Repetitions 1 `
  -Seed 2026
```

### 5. Run the main experiment

```powershell
.\run_main.ps1 `
  -Config "model-config.yaml" `
  -Repetitions 3 `
  -Seed 2026
```

The launcher validates the repository and provider, creates an immutable manifest, runs paired Linear/Async episodes, aggregates scores, and audits the result. See the [main experiment policy](experiments/formal-47/README.md) for selection, coverage, and resume rules.

### Run an agent system with Track B

```powershell
python -m pip install -e ".[track-b-claude]"
Copy-Item configs/track-b/claude-code.example.yaml track-b-config.yaml
python -m async_rbench.track_b doctor --config track-b-config.yaml
python -m async_rbench.track_b conformance --config track-b-config.yaml --output artifacts/track-b/conformance
```

Track B also supports `track-b-codex`, `track-b-langgraph` and `track-b-openai` extras. Codex CLI uses the participant's saved ChatGPT login. See the [Track B guide](docs/track-b.md) for paired runs and custom `ModelBackend`, `ContextBuilder`, `DelegationPolicy`, `AgentPolicy`, and `LifecycleHooks` implementations.

> [!IMPORTANT]
> Keep API keys, raw traces, private event truth, and restricted evaluator data local. Public submissions contain only allowlisted aggregate results.

## 📊 Leaderboard and Metrics

The [public leaderboard](https://pope8zdt.github.io/Async-RBench/leaderboard/) opens with the primary DRS view. The BTS view compares task correctness between execution modes.

| View | Measurement | Ranking |
| --- | --- | --- |
| **DRS** | Dynamic replanning quality under asynchronous events | Higher is better |
| **Linear BTS** | Base-task correctness in Linear mode | Component score |
| **Async BTS** | Base-task correctness in Async mode | Component score |
| **BTS difference** | Async BTS − Linear BTS | Higher is better |

Scores use a 0–100 scale. Complete reviewed results receive formal ranks; incomplete coverage remains visibly provisional. Coverage, execution status, materials review, and independent reproduction are separate facts.

The eight event themes are:

1. Delayed authoritative results
2. Stale and out-of-order results
3. Partial-to-complete results
4. Conflicting valid results
5. Duplicate and replayed completions
6. Child-task failures
7. Scope and dependency changes
8. Stragglers under resource pressure

Metric definitions and per-episode scoring are frozen in [`evaluation_contract.json`](evaluation_contract.json). Theme definitions live in [`event_taxonomy.json`](event_taxonomy.json).

## 📤 Submit Results

Participants execute the benchmark locally and submit a public aggregate package. Packaging excludes credentials, provider configuration, raw case scores, traces, and local paths.

```powershell
$benchmarkCommit = git rev-parse HEAD
python -m async_rbench.submissions package `
  --root . `
  --manifest artifacts/experiments/MY_RUN/manifest.json `
  --benchmark-commit $benchmarkCommit

python -m async_rbench.submissions check --root .
```

Read the [submission and review guide](submissions/README.md), then use the [Track A submission form](https://github.com/pope8zdt/Async-RBench/issues/new?template=benchmark-result.yml). Track B produces development results that remain separate from the Track A leaderboard.

## 📁 Repository Structure

```text
Async-RBench/
├── async_rbench/          # Kernel, runtime, scoring, and aggregation
│   └── track_b/           # Agent frameworks and custom harness API
├── adapters/              # Executable adapter entry points
├── cases/                 # Registered benchmark tasks
├── configs/               # Model profiles and runtime configuration
├── experiments/           # Versioned experiment definitions
├── schemas/               # Machine-readable contracts
├── submissions/           # Aggregate result packages and reviews
├── website/               # Static public website
├── docs/                  # Protocol and operator documentation
├── run_case.ps1           # Single-task paired launcher
└── run_main.ps1           # Main experiment launcher
```

Generated experiments belong under `artifacts/experiments/` and remain outside version control.

## 📚 Documentation

- [Website tutorial](https://pope8zdt.github.io/Async-RBench/docs/)
- [Chinese operator runbook](docs/CASE_RUNBOOK.zh-CN.md)
- [Evaluation protocol](PROTOCOL.md)
- [Adapter protocol](ADAPTER_PROTOCOL.md)
- [Kernel contract](docs/kernel-contract.md)
- [Adapter contract](docs/adapter-contract.md)
- [Result and termination contract](docs/async-rbench-result-contract-and-termination.md)
- [Evaluation tracks](docs/evaluation-tracks.md)
- [Track B agent systems](docs/track-b.md)
- [Codex CLI + Luna live validation](docs/reports/2026-09-07-track-b-codex-luna.md)
- [Submission and review guide](submissions/README.md)

## 🥰 Citation

If you use Async-RBench in your research, please cite the repository and the exact release used for evaluation:

```bibtex
@software{async_rbench_2026,
  title   = {Async-RBench: Benchmarking Asynchronous Result Integration and Dynamic Replanning},
  author  = {Async-RBench Contributors},
  year    = {2026},
  version = {11.0.0},
  url     = {https://github.com/pope8zdt/Async-RBench}
}
```

## 📧 Contact

Use [GitHub Issues](https://github.com/pope8zdt/Async-RBench/issues) for questions, bug reports, and result-submission support.
