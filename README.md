# Async-RBench

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

## Repository layout

- `async_rbench/`: execution, evaluation, adapter, and audit implementation;
- `cases/`: all 201 registered case instances, including evaluator-only private bundles;
- `configs/`: calibration plans and versioned model-profile templates;
- `schemas/`: machine-readable artifact schemas;
- `tests/`: framework unit and integration tests;
- `scripts/`: case production, native-runtime, and audit utilities;
- `docs/`: architecture and environment-specific instructions;
- `upstream/`: optional external source/native material; not included in Git because of size and nested repository history.

Only `(case_id, instance_id)` pairs listed in `cases/registry.json` are official registered instances. Calibration and development instances may be used for framework verification. Held-out test instances must not be used for prompt, adapter, threshold, or verifier development.

Terminology: **case family** means one of the eight `primary_event_theme` categories. `case_id` identifies a registered case within a family, and `instance_id` identifies one immutable instance. The registry key `case_families` is retained only as a legacy schema-v2 field; its entries are registered cases, not the eight families.

## Evaluation status

The dataset composition and Track A statistical design are locked, but the evaluation contract remains a development contract. Pilot runs are diagnostic and cannot be reported as a frozen leaderboard result.

- Contract: `9.1.0-dev`, status `development`;
- Dataset: 201 instances — calibration 82, development 30, test 89;
- Primary Track A outcome: Async Dynamic Control Score;
- Secondary summary: 80% dynamic control + 20% semantic task score.

## Protocol references

- [Evaluation protocol](PROTOCOL.md)
- [Adapter protocol](ADAPTER_PROTOCOL.md)
- [Reference scaffold](REFERENCE_SCAFFOLD.md)
- [Evaluation contract](evaluation_contract.json)
- [Dataset policy](dataset_policy.json)
- [Frozen Track A design](%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1-frozen-track-a.md)

Never place API keys, `.env` files, model credentials, experiment outputs, or participant-visible copies of private evaluator data in Git.
