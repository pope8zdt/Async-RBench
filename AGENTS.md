# Current experiment scope

- The public leaderboard reports only the fixed **47-case main experiment** in `experiments/formal-47/instances.txt`. `cohort.json` defines the selection digest, eight theme counts, three repetitions, seed and current model panel.
- The selection was supplied by the user from `artifacts/run-configs/formal-47-instances.txt`. Do not rediscover membership from completed runs, scores, filenames or historical data splits.
- Calibration/development/test labels remain historical registry metadata. They do not select or partition the main-47 leaderboard. The 61-case cohort is historical reference, not the active leaderboard denominator.
- Use `python -m async_rbench.main_experiment check` and `experiments/formal-47/run.ps1` for the current main experiment. Preserve old manifests, raw results, existing runs and the frozen per-episode scoring contract.
- Website source is `website/`. Its exporter reads only selected main-experiment episodes, rejects ambiguous duplicate attempts and exports allowlisted aggregates. Incomplete coverage must remain visible; provisional values are not full 47-case scores or independently verified results.
