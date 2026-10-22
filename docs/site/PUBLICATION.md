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
Preserve reduced-motion styles and keyboard access. The submission guide omits
the footer background-pause button at the owner's request; other pages retain
their controls. Background motion still respects reduced-motion preferences
and pauses while the page is hidden.
Evaluation instructions live in the repository, not in a homepage wizard.
After editing, run both test suites and inspect desktop views before publishing.
The owner requests desktop-only visual work; retain existing small-screen rules
without extending that scope. Pages deploys only after validation.

For desktop typography checks, compare the framework, chart and guide subheadings,
the two charts' count labels, and the guide's step/prose left edges in both
languages. The guide uses the homepage's outer frame and a narrower reading column;
keep its prose aligned with step text rather than the step numbers.
Desktop Tasks charts reuse the experiment figures' teal, coral and slate-blue
fills. Keep labels in the site's text color and retain explicit counts and
category names, so color is not the only way to read the charts.

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

### Interface terminology

Keep the same English term for the same concept across the homepage, submission
guide and Data viewer. Use sentence case for interface headings and labels.
Use these pairs when editing explanatory copy:

| English | Chinese | Usage |
| --- | --- | --- |
| evaluation | 测评 | The benchmark procedure; `benchmark` names the benchmark itself. |
| main agent / subagent | 主代理 / 子代理 | Actors; a `subtask` is the work assigned, not the actor. |
| run / repetition | 运行 / 重复 | One execution versus a repetition of an evaluation setting. |
| result delivery / result presentation | 结果交付 / 结果呈现 | Distinct recorded events; do not use interchangeably. |
| task success / task success rate | 任务成功 / 任务成功率 | A run's outcome versus an aggregate percentage. |
| validation / maintainer review / approval | 校验 / 维护者审核 / 审核通过 | Automated checks, human review and the approval decision are distinct. |
| review decision | 审核结果 | Do not label it `evaluation result` or `Check your result`. |
| result summary / original evidence | 结果摘要 / 原始证据 | The public summary versus private supporting files. |
| community results / community leaderboard | 社区结果 / 社区榜单 | The results tab versus the destination leaderboard. |
| archived records / trace | 归档记录 / 轨迹 | Selected event records are not a complete trace. |
| receipt / workflow | 回执 / 工作流 | Use `workstream` for concurrent agent work, not a GitHub workflow. |

Retain the paper names Dynamic Replanning Score (DRS) and Event Response Contract
(ERC), and the result-delivery labels Async and Batched. The eight short scenario
labels follow the paper: Delay, Stale, Conflict, Replay, Partial, Failure, Scope
and Straggler; the Tasks section spells out their meanings. Evaluation task
selection and repetitions are configurable; the paper's 200-task, three-repeat
experiment is not a universal instruction for running the benchmark. Editorial
changes do not alter the community submission validation policy.

Do not rename API fields, CLI options, filenames, original event identifiers or
quoted log values to match this prose vocabulary. Preserve the paper abstract,
task release titles and figure labels unless the scientific source is revised.
Compare both languages for quantities, negation, scope and uncertainty; shorten
wording only when the meaning remains intact.

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
the maintainer, template and App. Both pages stay closed by default. An authorized
enabled build shows one submission button on the homepage; repository creation
and review-access links appear beside their steps in the guide. Neither page
uploads files or grants permissions. Disabling a previously enabled snapshot
removes those setup links again. The public guide covers participant submission
and checking the community result; maintainer operations remain documented in
`../submissions/PR_REVIEW.md`, not on this page. Do not link participants to the
private central workflow. Explain where to read their PR receipt, distinguish
validation from approval and a `published` receipt from a cached page, and use
only fields visible on the community leaderboard when describing how to find
an entry. Missing results should be discussed on the original private PR without
duplicating submissions or exposing evidence.

Build without a repository configuration for the local preview so community
loading stays local too. To verify the release configuration locally without
publishing, run:

```sh
python docs/site/publication.py --output dist/site-release-check --base-path /Async-RBench --participation github-private --repository-config docs/site/participation.json
```

No private deployment kit or policy belongs in the website document root.
