# Async-RBench website

Static public website; participants execute evaluations on their own computers. Track A provides real configuration generation and main-47 aggregates. Track B remains an explicitly labeled simulation.

Pages use concise Chinese/English copy and a persistent light/dark preference. New visitors start in Chinese with their system color scheme. Optional configuration, scoring rules and provenance are available in expandable sections; incomplete coverage and simulation labels stay visible.

The leaderboard defaults to DRS descending. The BTS view sorts by Linear minus Async descending and shows both component scores. Both views show this signed difference in place of the former coverage column; percentage coverage remains in model details. DRS bars use the 0–100 scale, and difference bars share a symmetric, search-independent scale. Missing either BTS component produces a missing difference, never zero; coverage and review eligibility still control formal ranking.

Public page copy uses “201个高质量任务” and shows eight-theme distribution using registered-instance counts. Case/instance distinctions and the main-cohort size remain in machine-readable data, without appearing in page copy. The leaderboard retains the fixed main cohort and presents coverage as percentages, with paired Linear/Async BTS and Async DRS views. Full coverage, execution status and review status are separate facts. The website has no participant-process telemetry. The public `run_main.ps1` entry forwards to the unchanged canonical experiment launcher.

## Develop and build

Use Node 22.13+ and Python 3.9+ from a full repository checkout. From `website/`:

```powershell
python -m pip install -r scripts/requirements.txt
npm ci
npm run dev
```

`npm run build:static` generates `out/`. It first regenerates `public/data/corpus.json` and `public/data/leaderboard.json`; these derived files are ignored by Git. The catalog emits only counts and a registry digest. The leaderboard merges the validated versioned main snapshot with complete, separately reviewed submissions. All detail routes are rendered during the build. Optional `NEXT_PUBLIC_BASE_PATH=/repository-name` supports project hosting paths.

## Refresh main-experiment results

```powershell
python scripts/refresh_results.py --runs-root PATH_TO_AUTHORIZED_CHECKOUT
python scripts/refresh_results.py --runs-root PATH_TO_AUTHORIZED_CHECKOUT --write
```

The first command previews coverage. `--write` updates `public/data/experiments.json` atomically; neither command commits or publishes. Policy comes from this checkout's fixed main-47 cohort. The exporter rejects ambiguous attempts and checks manifest, score and configuration bindings. Missing scores remain missing; provisional metrics average only complete paired cases and their represented themes. Resources disclose measurement counts. No fixed child-model pool is required.

## Submit and review

See [the executable participant and maintainer workflow](../submissions/README.md). Entries live in `submissions/entries/<digest>.json`; a separate maintainer record in `submissions/reviews/` binds to the same content digest. The build includes only complete reviewed submissions in formal ranking. Main-experiment snapshots may still show incomplete, self-reported results.

Merge reviewed changes to `main` to trigger Pages validation/build/publication. Format checks and hashes do not authenticate scores or reviewer identity; repository maintainers authorize reviews and merges. No submission command calls models, transmits credentials or publishes raw artifacts.

## Verify

From `website/`:

```powershell
python -m unittest discover -s tests -p "test_*.py"
npm test
npm run build:static
npm run test:static
npx oxlint app components/site-shell.tsx components/leaderboard.tsx components/evaluate-form.tsx lib
```

From the repository root, also run `python -m unittest discover -s tests -p test_submissions.py` and `python -m async_rbench.submissions check --root .`. The unused starter UI catalog has existing lint findings and is outside this application lint scope.

Only `website/out/` is published. Model credentials, raw results and private case contents are excluded. See [deployment instructions](docs/deployment.md).
