# Paper website

The GitHub Pages source lives here; only generated static files are deployed.
There is no online evaluation service, credential collection or submission backend.

## Build and check

From the repository root, with Python 3.11+, the package dependencies and Node 22+:

```sh
python -m unittest discover -s docs/site/tests -p "test_*.py"
node --test docs/site/tests/logic.test.mjs docs/site/tests/trajectory.test.mjs
python docs/site/build.py --output dist/site --base-path /Async-RBench
```

The output must be new or empty. For a local root-path preview, use an empty base
path and a different output directory, then serve it with `python -m http.server`.
No npm dependencies are required. The Pages workflow runs these checks on changes
to the site or its public inputs and publishes only the generated artifact.

## Local trajectory preview

The homepage player is opt-in and does not change the default published page.
Keep source logs, the curation manifest and exported replay data outside the
repository. The exporter reads logs only: it never executes recorded commands,
calls model APIs, starts Docker, or invokes the judge.

```sh
python docs/site/trajectories.py --manifest <local-curation.json> --output <new-local-replay.json>
python docs/site/build.py --output dist/trajectory-preview --base-path "" --local-trajectories <new-local-replay.json>
python -m http.server 8766 --bind 127.0.0.1 --directory dist/trajectory-preview
```

Each curation entry names the episode, model, source SHA-256, bilingual labels,
milestone event sequences and explicitly reviewed command/evidence fields.
The exporter preserves event IDs, order and elapsed time; it omits unapproved
payloads, final answers, hidden checks and model reasoning. The hash must match
before export. Review the selected text before including it: pattern checks are
an additional guard, not a substitute for review. Do not serve the raw archive.

The player has key-moment and all-displayed-event views, with compressed playback
cadence over a true elapsed-time axis. "All displayed" is the filtered export,
not every raw record. Narration is separate from source fields. Presentations,
acknowledgments, file promotions and task success must not be conflated. Preserve
historical workflow counts even when the current protocol differs. Single-run
statuses do not update the frozen paper leaderboard.

The selected event leads with its recorded command, command excerpt or evidence
fields. Full exported JSON and cumulative state are available in disclosures;
opening or focusing a record pauses playback to preserve reading position.
Key moments form a chapter list beside the evidence (a horizontal strip on
phones). The event picker is available in the all-displayed-event view.

Preview builds reject the normal project base path; the player also refuses
non-loopback hosts. These checks are not access control for static files: never
upload a preview build. Default builds neither discover nor copy local logs.

## Sources and maintenance

- `data/paper-results.json` transcribes Tables 3 and 4 and Figures 3 and 6 of the
  manuscript v26 dated 2026-09-29. The source SHA-256 and score scales travel
  with the JSON download. These are paper-reported values, not a recomputation
  or independent reproduction of experiments.
- Keep the paper's reported task-success differences: they were calculated
  before rounding, so subtracting the displayed rates can change the last digit.
- Task counts and catalog metadata come from the public registry, release
  manifest and `public/case.yaml`. The catalog allowlist excludes private
  per-task scenario labels, solutions, verifiers and traces.
- Figures are reused from the repository's `assets/`; Figure 6 was refreshed
  from page 9 of manuscript v26 (200 dpi; crop in pixels: x=294,
  y=230, width=1114, height=459). Gemini Native's subagent value is 58.1.
  The private PDF is not included. The profile download is the current
  public template.
- Update Chinese and English text together. Preserve URL paths, keyboard access,
  responsive ranked lists and readable content without JavaScript. The homepage
  presents examples and results before framework details; avoid decorative
  section numbering, repeated promotional copy and nested card containers.
- Use body text for explanations and reserve secondary color for short metadata.
  Consolidate repeated notes; keep provenance and runtime requirements clear.
  Check the README result tables against the same frozen data as the website.
- The evaluation page links to the repository's judge-access issue form and
  setup guide. Access and compatible-bundle availability require maintainer
  confirmation; the site does not distribute hidden scoring materials.
- DRS bars are static score meters, not loading indicators. Their scale is always
  0–100, including the mean and model-detail score; do not normalize to the best
  model or introduce unreported performance bands. Numeric labels remain visible.
- The leaderboard presents Table 3 data as ranked cards, not a reproduction of
  the paper's table layout. Each compact card shows rank, model icon and name,
  Calls and the DRS bar, followed by all eight scenario means with sample SD.
  Scenario scores and the separate paper-mean summary are always visible,
  including without JavaScript. Scenario maxima are bold; Calls is cost, not a
  performance score. Paper means remain in a separate, unranked summary.
- Model-family icons are local SVGs from LobeHub Icons, with their revision and
  MIT notice in `assets/model-icons/`. Keep this notice in the built artifact.
  They identify the models, not version-specific capabilities or endorsement.
- Table 4 task success has its own ranked list. Both lists start in paper order
  and share the agent search. DRS ranking can also use a scenario mean; task
  success has an independent ordering control. Tied scores share a rank;
  filtering preserves ranks from the full nine-agent comparison.
  CSV retains its original aggregate columns and appends scenario means and SDs.
- The overview uses a three-agent preview; the complete nine-agent comparison,
  unranked paper mean and task-success results remain on the leaderboard page.
- Editable SVG diagrams in `assets/` explain the Async evaluation pipeline
  and evidence flow. The narrow-screen overview uses a vertical layout.
  Async is the main setting; Batched appears as an experimental baseline in
  the task-success comparison and protocol, not as a parallel homepage focus.
  These are website schematics, not manuscript figure replacements or runtime
  traces. The duplication walkthrough is explicitly illustrative. Original
  manuscript result figures and the frozen numerical data remain unchanged.
- Old provisional result links show a historical-record notice. The original
  website and snapshots remain in Git history; they are not paper leaderboard rows.

When the manuscript changes, review the reported values and source metadata,
update the figures if needed, run both test suites, and inspect desktop/mobile
rendering before publishing. Do not silently merge a partial run into the paper
table or describe build checks as score verification.
