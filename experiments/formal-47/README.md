# Main experiment: 47 cases

This is the active Async-RBench v11.0.0 main experiment and website leaderboard cohort. The authoritative membership is [instances.txt](instances.txt), promoted from the user-provided `artifacts/run-configs/formal-47-instances.txt`. [cohort.json](cohort.json) freezes its digest and run plan.

- Exactly 47 distinct registered `seed-1` instances, spanning eight themes.
- Each model runs Linear and Async three times per case: **282 episodes per model**.
- Seed 2026; incentive guidance. The current main panel is GPT-5.6 Luna, GPT-5.6 Terra, Claude Sonnet 5 and DeepSeek V4 Flash.
- Historical registration labels (26 calibration, 4 development, 17 test) are metadata only. The leaderboard includes the entire fixed cohort without a split filter. The corpus still has 201 registered instances; those outside the 47 do not enter this main experiment's statistics.

## Run locally

From the benchmark repository root, with the usual Python/Docker dependencies:

```powershell
python -m async_rbench.cli validate --release
python -m async_rbench.main_experiment check --root .
.\experiments\formal-47\run.ps1 -Config "model-config.yaml" -Repetitions 3 -Seed 2026
```

Outputs use `artifacts/experiments/formal-47-<timestamp>/`. Resume with the same config and `-ExperimentRoot <existing-directory> -Resume`. Existing per-case batch runs may retain their historical directory names; membership is always the 47-instance allowlist. Do not rewrite old manifests, delete scores, restart running jobs, or repurpose a historical 61-case manifest as a 47-case run.

`results.json` is the main-47 summary, produced by the same `async_rbench.main_results` aggregator as the website. `historical-split-diagnostics.json` retains the old split-filtered aggregate for diagnosis only. To regenerate a single run without rerunning agents, use `python -m async_rbench.main_results . --manifest <run-directory>/manifest.json --output <run-directory>/results.json`.

## Website statistics

Run `python website/scripts/export_results.py . --output website/public/data/experiments.json` from the repository root. The exporter uses current-panel legacy `batch-<model>-*` manifests and explicitly declared `formal-47` manifests, filters their episodes by exact membership, and verifies each score against its episode, manifest digest, frozen contract, score policy, case/verifier bindings and paired seed/configuration. Only the historical split eligibility gate is disregarded; Track A conformance and protocol requirements still apply. Duplicate attempts for one model/instance/mode/repetition are an error requiring explicit source resolution. Older diagnostic snapshots and the other 14 cases from the historical 61-case cohort are excluded.

The main plan was fixed from the 47 cases reached by Terra at the documented drain checkpoint; this provenance is recorded in `cohort.json`. It is not represented as an independently held-out sample.

For each metric: average the three repeats within each case, then cases within each theme, then the eight themes equally. A case is complete only when all six episodes are scored and the three primary measures are available. While work is incomplete, provisional values use only such complete cases and their represented themes; coverage is shown explicitly, and full-cohort fields remain null. Missing scores are never treated as zero or silently dropped from the planned denominator. Full coverage is distinct from publication review or independent reproduction.

The historical [61-case cohort](../formal-61/README.md) remains available for reproducing earlier runs. It is not the active website leaderboard cohort.
