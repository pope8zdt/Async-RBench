# Paper website

The GitHub Pages source lives here; only generated static files are deployed.
There is no online evaluation service, credential collection or submission backend.

## Build and check

From the repository root, with Python 3.11+, the package dependencies and Node 22+:

```sh
python -m unittest discover -s docs/site/tests -p "test_*.py"
node --test docs/site/tests/logic.test.mjs
python docs/site/build.py --output dist/site --base-path /Async-RBench
```

The output must be new or empty. For a local root-path preview, use an empty base
path and a different output directory, then serve it with `python -m http.server`.
No npm dependencies are required. The Pages workflow runs these checks on changes
to the site or its public inputs and publishes only the generated artifact.

## Sources and maintenance

- `data/paper-results.json` transcribes Tables 3 and 4 and Figures 3 and 6 of the
  manuscript supplied on 2026-09-26. The source SHA-256 and score scales travel
  with the JSON download. These are paper-reported values, not a recomputation
  or independent reproduction of experiments.
- Keep the paper's reported task-success differences: they were calculated
  before rounding, so subtracting the displayed rates can change the last digit.
- Task counts and catalog metadata come from the public registry, release
  manifest and `public/case.yaml`. The catalog allowlist excludes private
  per-task scenario labels, solutions, verifiers and traces.
- Figures are reused from the repository's `assets/`; Figure 6 was refreshed
  from page 9 of the supplied manuscript (300 dpi; crop in pixels: x=450,
  y=346, width=1650, height=692). It preserves the manuscript's Gemini Native
  subagent value, 55.5. The figure's call bars and the prose's reported
  7.5–10.2% increase do not fully reconcile; both remain as reported, with a
  note on the results page. The private PDF is not included. The profile
  download is the current public template.
- Update Chinese and English text together. Preserve URL paths, keyboard access,
  horizontal table scrolling on mobile and readable content without JavaScript.
- DRS bars are static score meters, not loading indicators. Their scale is always
  0–100, including the mean and model-detail score; do not normalize to the best
  model or introduce unreported performance bands. Numeric labels remain visible.
- Old provisional result links show a historical-record notice. The original
  website and snapshots remain in Git history; they are not paper leaderboard rows.

When the manuscript changes, review the reported values and source metadata,
update the figures if needed, run both test suites, and inspect desktop/mobile
rendering before publishing. Do not silently merge a partial run into the paper
table or describe build checks as score verification.
