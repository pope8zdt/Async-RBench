# Public website

`published/` is the editable source snapshot for the public website. It contains
the project homepage, dynamic cover and separate task/archived-record browser.
Earlier generators remain available for
data and layout development; they are not the Pages deployment source.

The snapshot uses root-relative links. `publication.py` validates it and adds
the GitHub project prefix when building, including JavaScript-generated URLs.

```sh
python -m unittest discover -s docs/site/publication-tests -p 'test_*.py'
node --test docs/site/publication-tests/*.test.mjs
python docs/site/publication.py --output dist/site --base-path /Async-RBench
```

Use a new or empty output directory. To preview the built project URL, serve its
parent and place the output at `preview/Async-RBench`, then open
`http://127.0.0.1:8000/Async-RBench/`. The build performs no API calls or evaluation.

## Data boundary

- Paper leaderboard data, the corpus, configuration template, PDF and experiment
  figures are protected by `publication-integrity.json`. Update those hashes only
  when deliberately updating the corresponding scientific source.
  The local `.gitattributes` also disables line-ending conversion for these files.
- `data/trajectories.public.json` contains selected, previously displayed event
  fields from six archived runs. It is not a complete trace or a new evaluation.
  Source hashes and original sequence numbers retain provenance. Model messages,
  hidden judges, local source paths, credentials and local trial outputs are not
  included. Descriptions distinguish observations from interpretations.
- No `.local.json` bundles or raw `.jsonl` logs are accepted by the release check.
  Adding a case requires review of its fields and an explicit record allowlist.
- Model names, paper numbers, task names and English diagrams are not editorial
  copy. Preserve them when changing page prose or presentation.

## Editing

Edit the snapshot's HTML, CSS and modules directly. Keep diagrams in English;
Chinese and English interface text lives in paired language spans or module
labels. `publication_views.py` fills the marked placeholders from the protected
public data at build time; do not hand-edit leaderboard numbers in HTML.
Preserve pause controls, reduced-motion styles and keyboard access.
Evaluation instructions live in the repository, not in a homepage wizard.
After editing, run both test suites and inspect
desktop and mobile views before publishing. Pages deploys only after validation.

The October 19 editorial pass makes framework explanations visible, combines the
paper metrics into one table, replaces scrolling dataset badges with distribution
tables, and moves the catalog and six selected archives into `/tasks/`. Legacy
page URLs redirect to the corresponding canonical section. The archived excerpts
are explicitly not a full trajectory replay. The cover and margin movement remain.

The Tasks overview uses a difficulty ring and an initial-subtask histogram,
computed from the protected public corpus, followed by compact scenario counts.
It does not display task sources or introductory prose. The histogram counts
tasks, not subtasks; its horizontal labels are initial subtasks per task,
grouped as 2, 3 and ≥4 (73, 40 and 87 tasks in the current corpus).
Its Data viewer link opens the separate task catalog and archived records; no
individual tasks appear on the homepage. Per-task scenario labels and detailed
evaluation annotations stay private.

The homepage framework explanation summarizes the execution and evaluation flow.
It expands ERC and DRS on first use, but leaves formulas and scoring details to
the paper and the existing protocol link beside the leaderboard.

Community results use a separate tab. Both approved public-summary schemas are
validated before rendering; original evidence, receipt identifiers and review
links are never inserted into the board. The native PR worker is implemented;
intake requires permissions, secrets, policy and the trusted workflow
to be configured and activation to be authorized. An old `enabled` flag cannot turn
it on. The explicit `private-pr-v1` public configuration in
`../submissions/github-only/pr-site-config.example.json` supplies the App,
participant template, human maintainer and separate summary URL. Setting
`enabled: true` only renders the entry; it does not provision or activate GitHub.
Use it only after explicit rollout approval and deployment verification. The operational instructions are
in `../submissions/PR_REVIEW.md`; the legacy Issue adapter remains separate.

The Pages build consumes `participation.json`, which is public configuration,
not a credential. The owner authorized activation on 2026-10-20 and explicitly
waived real-submission acceptance testing. The release sets `enabled: true`;
the default preview remains closed. Its community URL must be reachable before
publishing. Raw evidence and private policy are never deployment assets.

`/submission-guide/` uses the same entry configuration as the homepage, including
the maintainer, template and App. Both pages stay closed by default; an authorized
enabled build adds repository-creation and App-installation links to both pages.
Neither page uploads files or grants permissions. Disabling a previously enabled
snapshot removes those links again. Participant submission, maintainer review and
sync confirmation have separate linked sections. The guide distinguishes an
Actions run succeeding from a particular result appearing in the Community tab.

Build without a repository configuration for the local preview so community
loading stays local too. To verify the release configuration locally without
publishing, run:

```sh
python docs/site/publication.py --output dist/site-release-check --base-path /Async-RBench --participation github-private --repository-config docs/site/participation.json
```

No private deployment kit or policy belongs in the website document root.
