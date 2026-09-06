# Participant submissions

The public leaderboard uses the fixed 47 instances in `experiments/formal-47/instances.txt`, three repetitions, and paired Linear/Async execution: 282 episode slots per run. Historical dataset splits and the historical 61-case cohort do not select leaderboard membership. Keep the frozen scoring contract and declared manifest unchanged. There is no required fixed child-model pool; a child model can remain a private runtime configuration choice.

All commands below run from the repository root with Python 3.9 or newer. Submission validation uses only the Python standard library. Website corpus generation also requires PyYAML: `python -m pip install -r website/scripts/requirements.txt`. Running the benchmark itself still requires its normal runtime dependencies and credentials.

## Participant: package a declared run

1. Check the cohort with `python -m async_rbench.main_experiment check` and execute the current main experiment using `experiments/formal-47/run.ps1`. Use a declared main-47 manifest, with the correct scoring contract and all 282 slots. Packaging also accepts new participant model names.
2. Record the exact 40-character lowercase benchmark commit used for execution. Keep provider configuration, credentials, episode scores and traces local. If useful, supply a sanitized reproducibility configuration file to `--config`; only its SHA-256 is included, never its contents or path. Omit `--config` when no shareable configuration identity is available.
3. Package and validate the result:

```powershell
$benchmarkCommit = git rev-parse HEAD
python -m async_rbench.submissions package --root . --manifest artifacts/experiments/MY_RUN/manifest.json --benchmark-commit $benchmarkCommit --config configs/my-public-run-settings.json
python -m async_rbench.submissions check --root .
```

The package command prints `submissionId` and writes `submissions/entries/<submissionId>.json`. The optional `--output` selects another destination; copy the file into `entries` under its digest filename before repository validation or publication. Existing output files are never overwritten. A single file can also be checked with:

```powershell
python -m async_rbench.submissions validate --root . --input submissions/entries/SUBMISSION_ID.json
```

Submit only the generated entry JSON through the repository contribution process. A participant entry cannot contain a review assertion. Changes to aggregate contents, benchmark commit or configuration hash produce a new submission ID. Distinct runs of the same model can coexist. Exact duplicate content is the same submission and is rejected if stored twice.

Packaging always starts from the manifest-bound main-experiment exporter. It includes an allowlist of aggregate metrics, coverage counters, source digests, optional theme and resource aggregates, the benchmark commit and optional configuration digest. It excludes raw per-case scores, traces, environment variables, provider configuration, credentials and local paths. Inspect model labels and any public metadata before sharing. Hashes identify bytes; they do not make secret material suitable for publication.

## Coverage and metrics

An entry is `self_reported`; execution status is `unknown`. Missing scores never imply that a process is running. Complete coverage requires all 47 selected cases with valid paired scores across three repetitions. Incomplete entries retain observed metrics and counters, but formal Linear BTS, Async BTS and Async DRS remain null.

Scores average repetitions per case, cases within each theme, and then represented themes equally. An incomplete observed value is provisional and uses only fully paired cases; it is not a 47-case result. Missing theme metrics remain null. Resource means, when present, use measured episodes among completed pairs and disclose the number of measured episodes.

Only complete entries with a separate matching maintainer review enter the public accepted-record list. Complete unreviewed entries and reviewed incomplete entries are excluded. This rule does not alter the existing main-experiment snapshot, where incomplete coverage remains visible.

## Maintainer: review and publish

Validate the participant entry and inspect its reproducibility materials. The package must already be present as `entries/<submissionId>.json` for the repository-wide check to accept its review. Create the review separately:

```powershell
python -m async_rbench.submissions review --root . --input submissions/entries/SUBMISSION_ID.json --status materials_reviewed --reviewer "Maintainer name"
python -m async_rbench.submissions check --root .
```

`materials_reviewed` means a maintainer reviewed the supplied materials. It does not mean the maintainer reran the experiment. Use `independently_reproduced` only after independently reproducing the result, and provide a public HTTPS reference documenting the reproduction:

```powershell
python -m async_rbench.submissions review --root . --input submissions/entries/SUBMISSION_ID.json --status independently_reproduced --reviewer "Maintainer name" --evidence-url https://github.com/OWNER/REPOSITORY/issues/123
```

The review is written to `submissions/reviews/<submissionId>.json` with a timestamp, reviewer label and an exact binding to the entry's content digest. Commands refuse to overwrite an existing review. Treat published entries and reviews as immutable history; corrections require an explicitly reviewed repository change, and changing entry content requires a new digest-bound review. Never silently upgrade a review status during a website rebuild.

Keep authority over `submissions/reviews` with trusted maintainers in the repository review process. A contributor can type a maintainer name or invent an evidence URL: **the JSON checker validates structure, consistency and digest binding, not score authenticity, reviewer identity or the truth of reproduction evidence.** A matching hash is not a signature. CI passing is not independent score attestation. Review files from participant contributions require maintainer inspection and authorization before merge.

After validation, use the website's documented data preparation/build workflow and the repository's GitHub Pages publication process. No submission command runs models, sends credentials, uploads raw artifacts, or deploys the website.

## Schema and integrity

Schema version 1 has exactly these envelope fields: `schemaVersion`, `submissionId`, `contentSha256`, `cohort`, `benchmarkCommit`, `configSha256`, and `record`. `cohort` includes `id`, `case_count`, `selection_sha256`, `repetitions`, and `theme_counts`, checked against the repository's fixed selection. The record preserves the scoring-contract version and strict aggregate allowlist.

`submissionId` and `contentSha256` are the SHA-256 of UTF-8 JSON for all other envelope fields, with sorted keys, no extra separators or ASCII escaping, and no non-finite numbers. Generated snapshot time is excluded. Unknown fields, duplicate JSON keys, booleans in numeric fields, non-finite numbers, invalid counters, inconsistent nulls, wrong cohort bindings and altered content are rejected. Stored entry and review filenames must match the submission digest; duplicate entries/reviews and review bindings to absent or altered entries fail the check.

The Python integration interfaces are `package_run(root, manifest_path, *, benchmark_commit, config_path=None)`, `validate_submission(package, cohort)`, and `load_accepted(root)`. Accepted records receive a unique digest `id`, `submissionId`, `reviewStatus`, `benchmarkCommit`, `configSha256`, `reviewEvidenceUrl`, `published=True` and `executionStatus='unknown'`.
