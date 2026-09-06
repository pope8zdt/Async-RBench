# Current experiment scope

- Public website wording is uniformly **201个高质量任务**. Do not display the 47-case cohort size or separate case/instance totals in page copy. Use instance-based theme counts for the public task distribution and percentages for experiment coverage. This presentation rule does not alter the canonical cohort, exporter, raw data or scoring denominator.
- Keep public pages concise: one-line introductions, primary controls and data first; put detailed rules and provenance in tutorials or disclosures. All user-facing copy supports Chinese/English through the shared preferences provider; theme surfaces use CSS variables for light/dark support. Preserve concise provisional and simulation status labels.

- The public leaderboard reports only the fixed **47-case main experiment** in `experiments/formal-47/instances.txt`. `cohort.json` defines the selection digest, eight theme counts, three repetitions, seed and current model panel.
- The selection was supplied by the user from `artifacts/run-configs/formal-47-instances.txt`. Do not rediscover membership from completed runs, scores, filenames or historical data splits.
- Calibration/development/test labels remain historical registry metadata. They do not select or partition the main-47 leaderboard. The 61-case cohort is historical reference, not the active leaderboard denominator.
- Use `python -m async_rbench.main_experiment check` and `experiments/formal-47/run.ps1` for the current main experiment. Preserve old manifests, raw results, existing runs and the frozen per-episode scoring contract.
- Website source is `website/`. Its exporter reads only selected main-experiment episodes, rejects ambiguous duplicate attempts and exports allowlisted aggregates. Incomplete coverage must remain visible; provisional values are not full 47-case scores or independently verified results.

- Corpus data retains full registry counts for validation; public task descriptions follow the wording rule above and use the task distribution, never the leaderboard denominator as the corpus total.
- Fixed child model pools are not a public experiment condition or submission requirement. Preserve historical raw metadata and per-episode scoring.
- Leaderboard offers paired BTS and DRS views. Incomplete coverage does not prove an execution is running; preserve separate coverage, execution and review statuses.
- Submission entries are aggregate-only self-reports. Maintainer review records are separate and digest-bound; CI validation cannot authenticate scores or a reviewer identity.
