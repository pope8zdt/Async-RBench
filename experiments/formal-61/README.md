# Formal 61-Case Experiment

This directory is the authoritative formal evaluation entry point for
Async-RBench v11.0.0.

`paper-eval-existing-61.csv` freezes exactly 61 registered `seed-1` instances
in execution order. Their implementations are not copied here: every row
resolves to the unique canonical case under [`../../cases/`](../../cases/).
The current runnable cohort contains 61 of the planned 80 cases. It excludes
`gaia2-stockholm-moveout` and the 19 cases that have not yet been constructed.

## Prerequisites

- Python environment with the repository's evaluation dependencies installed;
- the selected model profile and its credentials;
- a running Docker Linux engine for actual episodes.

Run commands from the repository root.

## Validate the frozen cohort

This checks all 61 registrations and required case contracts without calling a
model or starting Docker workloads:

```powershell
python -m async_rbench.paper_eval check --root .
```

## Run the formal experiment

```powershell
.\experiments\formal-61\run.ps1 `
  -Config "configs/model-profiles/deepseek-v4-pro.yaml" `
  -Repetitions 1 `
  -Seed 2026
```

The launcher validates the repository and provider, creates an immutable
manifest, runs one Linear and one Async episode for every selected instance,
aggregates the results, and audits the run.

Outputs are written under:

```text
artifacts/experiments/paper-eval-existing-61-<timestamp>/
|-- manifest.json
|-- runs/
|   `-- run-binding.json
|-- results.json
|-- run-audit.json
`-- live.log
```

To resume an infrastructure-interrupted run, provide the same profile and the
existing output directory:

```powershell
.\experiments\formal-61\run.ps1 `
  -Config "configs/model-profiles/deepseek-v4-pro.yaml" `
  -ExperimentRoot "artifacts/experiments/paper-eval-existing-61-20260905-030000" `
  -Resume
```

Resume is rejected if the manifest, model profile, configuration contents,
runtime mode, resource policy, or retained score bindings differ from the
original run.

The calibration/development/test labels are preserved from the registered
cases. This is a reproducible execution cohort; it does not claim all 61 cases
are held-out.
