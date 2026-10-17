# GitHub submissions and community results

The main page prepares a public GitHub Issue draft. Participants sign in on
GitHub and submit it themselves. Maintainers review in the repository; a
permission-checked, read-only import adds approved results to a separate
community leaderboard. The website has no role selector or reviewer account.

The public section runs on **GitHub Pages** without a Python server or website
login database. Selecting a public submission file processes it in the browser;
it does not upload the file. GitHub handles login and the final posting action.
No model API or Docker execution is needed. Paper results remain separate.

## Preview

From the repository with the package installed:

```text
python -m async_rbench.submissions serve --port 8773
```

Open `http://127.0.0.1:8773/benchmark/#participate`. The Submit Results section
has only **Submit** and **Community**. It shares the main page's fonts, language,
theme and animated background. Instructions and the exact public draft stay
collapsed until requested. The server overlays this section on the local HTTP
response without rewriting the published site.

The community database is `dist/community/community.sqlite`, separate from the
paper data and the old simulation. `--data-dir` selects another private local
directory. The server binds only to `127.0.0.1`; do not expose it publicly.

## Participant: prepare and submit

1. Finish the evaluation and its `audit-run` check. Keep the original manifest,
   audit report and run directory, including each episode's `score.json` and
   `event_source.jsonl`.
2. Export a receipt from those original files. Substitute your paths, public
   names and the full 40-character code commit below. In PowerShell, use one
   line instead of the shell continuation characters.

```sh
python -m async_rbench.submissions export \
  --run-root runs/community --manifest community-manifest.json \
  --audit community-audit.json --agent "Your agent" --model "Your model" \
  --organization "Your organization" --code-revision YOUR_40_CHARACTER_COMMIT \
  --output community-receipt.json

python -m async_rbench.submissions prepare community-receipt.json \
  --output submission.json
```

3. Select **submission.json**, not the private receipt, in the website. The CLI
   checks the receipt before exporting this allowlisted public file. The browser
   previews the file without any upload. Inspect **Public summary**, then confirm that this
   summary may be public before choosing **Continue on GitHub**.
4. GitHub handles login and the final Issue submission. Opening the draft is
   not submission. Keep the receipt fingerprint in the Issue body unchanged.
5. Arrange private delivery of the receipt and complete original evidence
   with the maintainers. Do not attach raw traces, configurations, API keys,
   private judge files or the full receipt to the public Issue.

Only public agent/model/organization names, code commit, task coverage and the
receipt fingerprint enter the draft. The website does not save uploads
or send them to GitHub. The original receipt is **private review material**: it
contains a manifest, selected score fields and artifact fingerprints, but not
raw traces or configuration files.

A partial run can be checked and discussed, but cannot enter the community
ranking. Ranked submissions require all 200 registered tasks, three Async
repetitions, one model and the frozen incentive protocol.

## Maintainer: review and import

Review the original evidence privately. An automated consistency check is not
proof of authentic execution or an independent rerun. Review provenance,
settings and the reported behavior before approval.

On the existing submission Issue, add a new comment in this exact format:

```text
/async-rbench approve RECEIPT_SHA256
Reason for this decision and the checks performed.
```

Other actions are `request-changes`, `reject` and `withdraw`. Every decision
needs the exact receipt SHA-256 and a reason. The latest applicable comment
wins. Use a **new comment** for a new decision. Self-review is not accepted.
Only reviewers with repository write, maintain or admin permission count.

The importing maintainer signs in with GitHub CLI on their own machine
(`gh auth login`), then runs:

```sh
python -m async_rbench.submissions sync \
  --issue ISSUE_NUMBER --receipt community-receipt.json \
  --run-root runs/community --manifest community-manifest.json \
  --audit community-audit.json --judge-root /path/to/trusted/judge
```

This command performs **GitHub GET requests only**. It checks the importing
account and reviewer's repository permissions, derives the submitter from the
Issue author, binds approval to the exact receipt, re-reads the original local
evidence and compares it with the maintainer-owned benchmark and judge.
Tokens remain managed by GitHub CLI, never by the webpage.

Pending, rejected, change-requested and withdrawn decisions can be imported
with only `--issue` and `--receipt`. Approval requires all original evidence
paths and `--judge-root`. Imported decisions and their actors are retained in
the local audit history; only approved summaries appear on the community board.

Imports are explicit, **not automatic monitoring**. Re-run `sync` after any
Issue or review changes. An updated receipt needs a fresh hash-bound approval;
withdrawal removes its community entry at the next import. Nothing posts to
GitHub, changes a paper result or publishes the local board.

## Maintainer: publish the community snapshot

After importing all changed reviews, export only approved summaries:

```sh
python -m async_rbench.submissions export-board \
  --output docs/submissions/community.json
```

Review that JSON, commit it, and publish through the existing Pages workflow.
Do not commit the database, receipt, judge or original evidence. This manual
export is the only source of the website's community board; the paper leaderboard
is never merged with it. Re-sync and re-export after withdrawals or new decisions.
An approval comment alone does not update the live website.

The publication build adds the public participation UI to the reviewed snapshot
and validates the board's field allowlist. It rejects private fields, invalid
scores and links outside this repository. An empty board is intentional until
the first real submission is reviewed. Never publish synthetic test results.

## Validation and trust boundary

The importer rejects missing, duplicate or extra episodes; altered raw-byte
manifest bindings; incompatible contracts, case/verifier/runtime digests;
invalid modes, repetitions or score ranges; boolean/non-finite scores;
failed audit gates; and evidence drift. Scores are recomputed from validated
per-episode results, not an uploaded headline value. Original artifact hashes
are checked again before ranking. Uploaded JSON is data only: no URLs, archive
contents, commands or judge code are fetched or executed.

The board labels entries **Maintainer reviewed**, not independently verified.
The maintainer-supplied judge directory is the explicit trust root. Hashes
prove consistency with supplied files, not that an agent actually ran them.

## Tests

```text
python -m pytest tests/test_submission_artifacts.py tests/test_github_submissions.py tests/test_github_submission_server.py -q
python -m pytest -m "not docker" -q
node --test docs/submissions/ui/github-app.test.mjs docs/submissions/ui/app.test.mjs
```

Lifecycle tests exercise real artifact parsing, SQLite storage and HTTP
handlers. Only GitHub's transport is substituted with recorded-shaped test
responses. Synthetic evidence is confined to temporary test directories;
no sample results are seeded into the normal community board. Public posting
requires separate human confirmation; opening a GitHub draft does not post it.

## Earlier simulation

The explicit legacy command below remains for regression testing only. Its
selectable identities are **not authentication**, and its package format and
database are never imported into the GitHub workflow.

```text
python -m async_rbench.submissions.server --demo --port 8774
```

## Research behind the flow

- [OSWorld public evaluation](https://github.com/xlang-ai/OSWorld#public-evaluation): distinguish submissions from maintainer verification and trajectory inspection.
- [SWE-bench submission checklist](https://github.com/swe-bench/experiments/blob/main/checklist.md): require system identity and reviewable evidence.
- [Terminal-Bench integrity](https://www.tbench.ai/news/leaderboard-integrity-and-timeouts): comparable settings and withdrawal or resubmission.
- [Harbor Hub leaderboards](https://docs.harborframework.com/harbor-hub/leaderboards): preparation and inspection before publication.
- [GitHub Issue drafts](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-an-issue): human-controlled drafts with prefilled titles and bodies.
- [GitHub repository permissions](https://docs.github.com/en/rest/collaborators/collaborators#get-repository-permissions-for-a-user): verified repository reviewer roles.
