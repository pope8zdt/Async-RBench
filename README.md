# Async-RBench: Benchmarking Asynchronous Task Execution in LLM Agents

Async-RBench evaluates whether a main LLM agent can integrate independently
completing subagent results, respond to changed assumptions, and dynamically
replan toward a verified final state.

Version: 11.0.0  
Contract: frozen  
Release: `v11.0-paper`

This repository is the public paper release. It contains the evaluation
framework and the complete 200-task public benchmark. Formal scoring truth is
kept in a separately distributed judge bundle and is never included here.

## Benchmark at a glance

| Item | Frozen paper setting |
|---|---:|
| Public tasks | 200 case directories / 200 registered instances |
| Source balance | 40 each from GAIA2, MultiAgentBench, OSWorld, SWE-bench, and Terminal-Bench |
| Scenario balance | 8 asynchronous scenarios, 25 tasks each |
| Initial subtasks | 621 total: 73 two-subtask, 40 three-subtask, 87 four-or-more-subtask tasks |
| Difficulty | 104 medium, 96 hard |
| Dataset splits | 81 calibration / 30 development / 89 test |
| Delivery modes | Batched and Async |
| Repetitions | 3 per task and mode |
| Evaluated models | 9 |
| Main experiment | 10,800 episodes |

The paper evaluates Claude Sonnet 5, GPT-5.6 Terra, Qwen3.7 Plus, GLM5.3
Flash, GPT-5.6 Luna, DeepSeek V4 Pro, Qwen3.5 27B, Kimi K2.5, and Gemini 3
Flash High. The main agent and its children use the same model in each run.
The frozen experiment definition is in
[`paper_artifacts/experiment_manifest.json`](paper_artifacts/experiment_manifest.json).

## What is released

- `src/async_rbench/`: execution, scheduling, scoring, aggregation, audit, and
  adapter-conformance framework;
- `data/async-rbench/cases/`: the 200 participant-visible task bundles;
- `data/async-rbench/registry.json` and `release.json`: the frozen registry and
  corpus digest binding;
- `adapters/`: reference adapter entry points;
- `configs/`: public configuration templates and native-runtime dependency
  locks;
- `tests/`: public framework and release-contract tests;
- `paper_artifacts/`: the publication-safe main-experiment manifest.

Each public task contains only `public/`, `task/`, and `PROVENANCE.md`. Hidden
tests, solutions, mutation suites, event policy, verifier logic, oracle truth,
credentials, and run traces are not part of this repository.

## Installation

Python 3.11 or newer is required.

```bash
python -m venv .venv
python -m pip install -U pip
python -m pip install -e ".[test]"
```

Validate the public checkout:

```bash
async-rbench list
async-rbench validate-public
python -m pytest -q
```

The validation result for this release is:

```json
{"valid": true, "case_count": 200, "instances": 200}
```

## Running the paper protocol

The two paper-facing delivery modes share the same concurrent child execution:

- **Batched** (internal compatibility key `linear`) buffers eligible subagent
  results and presents them together after the required workflows terminate.
- **Async** (`async`) presents eligible results individually while the main
  agent continues working.

Create and execute a reproducible manifest with an explicitly supplied judge
bundle:

```bash
async-rbench validate-judge --judge-root <judge-root>
async-rbench certify-release --judge-root <judge-root>

async-rbench-eval make-manifest \
  --output manifest.json \
  --repetitions 3 \
  --guidance incentive \
  --seed 2026 \
  --execution-modes linear async \
  --judge-root <judge-root>

async-rbench-eval run-manifest \
  --manifest manifest.json \
  --output <run-directory> \
  --judge-root <judge-root>
```

The framework does not search for a private judge path implicitly. Generated
manifests bind all 200 public cases, their verifier digests, and the judge
release digest.

The frozen per-episode limits are 100 main-agent responses, 40 responses per
subagent, 16,384 output tokens per model response, at most 3 concurrent
participant-spawned children, and a 2,400-second episode timeout.

See [`PROTOCOL.md`](PROTOCOL.md), [`docs/cli.md`](docs/cli.md), and
[`docs/adapter-contract.md`](docs/adapter-contract.md) for the complete public
contract.

## Metrics

Async-RBench reports three paper-facing metrics:

1. Batched task success;
2. Async task success;
3. Async Dynamic Replanning Score (DRS).

For each target event, the process score `P` is the mean of the applicable
Change, Preserve, Forbid, and Verify components. With event outcome `O`,

```text
DRS_event = 100 * (P + O) / 2
```

DRS is reported only for Async runs and is independent of end-to-end task
success. Machine artifacts use the compatibility fields
`linear_base_task_score`, `async_base_task_score`, and
`async_dynamic_replanning_score`, storing values on `[0, 1]`; paper tables
display percentages. Scenario results average the 25 tasks within each
repetition, then report the mean and sample standard deviation across the three
repetition-level means. The overall result weights the eight scenarios equally.

The manuscript reports Async DRS values from 19.2 to 45.1 across the nine
evaluated models. Averaged across models, Async task success is 29.7% versus
26.0% under Batched delivery; tasks requiring full rebuilds show gains of
2.6--3.5 percentage points.

## Repository structure

```text
Async-RBench/
├── adapters/                 # adapter entry points
├── configs/                  # public templates and runtime locks
├── data/async-rbench/
│   ├── cases/                # 200 public task bundles
│   ├── registry.json         # 200 registered instances
│   └── release.json          # frozen public corpus binding
├── docs/                     # dataset, CLI, kernel, and adapter contracts
├── paper_artifacts/          # frozen paper experiment manifest
├── schemas/                  # public adapter-event schema
├── scripts/                  # release/runtime helpers
├── src/async_rbench/         # evaluation framework
└── tests/                    # public verification suite
```

## Licensing and citation

Original Async-RBench code and documentation are released under Apache-2.0.
Transformed upstream task materials retain their applicable upstream terms;
see [`NOTICE`](NOTICE) and
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).

Citation metadata is provided in [`CITATION.cff`](CITATION.cff). Until the
double-blind review is complete, the author fields remain anonymized in the
release metadata.
